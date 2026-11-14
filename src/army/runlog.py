"""H5: `army run -- <cmd>` runs a command and records it in runs.jsonl.

runs.jsonl is append-only. A `running` record is written before the command starts and a final record with
the same run_id when it ends: `completed` (exit 0), `failed` (non-zero) or `interrupted` (SIGINT/SIGTERM/SIGHUP).
Readers merge records by run_id, so a run that never got its final record still shows up; if its process is
gone it is reported as `lost` (e.g. army itself was SIGKILLed).

`--seed N` sets ARMY_SEED and PYTHONHASHSEED for the command. The script must read ARMY_SEED itself and seed
its RNGs (random, numpy, torch, ...); army cannot do that from outside the process.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from army import paths

GRACE_S = 10  # after forwarding a signal: wait this long, then SIGTERM; the same again, then SIGKILL
INTERRUPT_SIGNALS = [s for s in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, s)]


def _git(project: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(f: Path, rec: dict) -> None:
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()


class _Forwarder:
    """Forwards interrupt signals to the child's process group and escalates if it does not exit."""

    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.signum: int | None = None
        self.timers: list[threading.Timer] = []
        self.old: dict[int, object] = {}

    def _send(self, sig: int) -> None:
        if self.proc.poll() is not None:
            return
        try:
            if hasattr(os, "killpg"):
                os.killpg(self.proc.pid, sig)
            else:
                self.proc.send_signal(sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def handle(self, signum, _frame) -> None:
        if self.signum is not None:  # second interrupt: stop now
            self._send(getattr(signal, "SIGKILL", signal.SIGTERM))
            return
        self.signum = signum
        self._send(signal.SIGINT if signum == getattr(signal, "SIGHUP", None) else signum)
        for delay, sig in ((GRACE_S, signal.SIGTERM), (2 * GRACE_S, getattr(signal, "SIGKILL", signal.SIGTERM))):
            t = threading.Timer(delay, self._send, args=(sig,))
            t.daemon = True
            t.start()
            self.timers.append(t)

    def __enter__(self):
        if threading.current_thread() is threading.main_thread():
            for name in INTERRUPT_SIGNALS:
                s = getattr(signal, name)
                self.old[s] = signal.signal(s, self.handle)
        return self

    def __exit__(self, *exc):
        for t in self.timers:
            t.cancel()
        for s, h in self.old.items():
            signal.signal(s, h)
        return False


def _status(code: int, signum: int | None) -> str:
    killed_by = -code if code < 0 else None
    interrupts = {getattr(signal, n) for n in INTERRUPT_SIGNALS}
    if signum is not None or killed_by in interrupts:
        return "interrupted"
    return "completed" if code == 0 else "failed"


def run(cmd: list[str], project: Path, seed: int | None = None, out: str | None = None) -> dict:
    st = paths.state_dir(project)
    (st / "runs").mkdir(parents=True, exist_ok=True)
    runs_file = st / "runs.jsonl"
    started = datetime.now()
    run_id = f"{started:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    log_path = st / "runs" / f"{run_id}.log"
    sha = _git(project, "rev-parse", "HEAD")
    dirty = None if sha is None else bool(_git(project, "status", "--porcelain"))
    env = dict(os.environ, ARMY_RUN_ID=run_id)
    if seed is not None:
        env["ARMY_SEED"] = str(seed)
        env["PYTHONHASHSEED"] = str(seed)
    rec = {
        "run_id": run_id, "status": "running", "cmd": shlex.join(cmd), "cwd": str(Path.cwd()), "git_sha": sha,
        "git_dirty": dirty, "seed": seed, "started": started.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "pid": os.getpid(), "host": socket.gethostname(), "log": str(log_path), "out": out,
    }
    _append(runs_file, rec)

    t0 = time.monotonic()
    signum = None
    # Own process group: one Ctrl+C reaches the command once (via army), and its workers are stopped with it.
    # A background process group must not read the terminal, so stdin is detached only when it is a tty.
    popen_kw: dict = {}
    if sys.version_info >= (3, 11) and hasattr(os, "setpgid"):
        popen_kw["process_group"] = 0
    elif hasattr(os, "setpgid"):
        popen_kw["preexec_fn"] = lambda: os.setpgid(0, 0)
    try:
        stdin_tty = sys.stdin is not None and sys.stdin.isatty()
    except (ValueError, OSError):
        stdin_tty = False
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        try:
            proc = subprocess.Popen(cmd, cwd=Path.cwd(), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL if stdin_tty else None,
                                    text=True, errors="replace", **popen_kw)
        except OSError as e:
            msg = f"army run: cannot start {cmd[0] if cmd else ''}: {e}\n"
            sys.stderr.write(msg)
            log.write(msg)
            code = 127
        else:
            with _Forwarder(proc) as fw:
                with proc.stdout:
                    for line in proc.stdout:
                        sys.stdout.write(line)
                        sys.stdout.flush()
                        log.write(line)
                        log.flush()
                code = proc.wait()
                signum = fw.signum
    status = _status(code, signum)
    final = dict(rec, status=status, ended=_now(), duration_s=round(time.monotonic() - t0, 3),
                 exit_code=code, signal=signal.Signals(signum).name if signum else None)
    final.pop("pid", None)
    _append(runs_file, final)
    return final


def exit_status(rec: dict) -> int:
    """Shell-style exit code for `army run`: the command's code, or 128+N when it ended by signal N."""
    if rec.get("signal"):
        return 128 + int(getattr(signal, rec["signal"]))
    code = int(rec.get("exit_code", 1))
    return 128 - code if code < 0 else code


def _alive(rec: dict) -> bool:
    if rec.get("host") not in (None, socket.gethostname()):
        return True  # cannot check another machine; trust the record
    try:
        os.kill(int(rec["pid"]), 0)
    except (KeyError, ValueError, TypeError, ProcessLookupError):
        return False
    except PermissionError:
        return True
    return True


def recent(project: Path, n: int = 5) -> list[dict]:
    f = paths.state_dir(project) / "runs.jsonl"
    if not f.is_file():
        return []
    merged: dict[str, dict] = {}
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        rid = rec.get("run_id") or f"?{len(merged)}"
        merged[rid] = {**merged.get(rid, {}), **rec}
    out = []
    for rec in merged.values():
        if "status" not in rec:  # records written before statuses existed
            rec["status"] = "completed" if rec.get("exit_code") == 0 else "failed"
        elif rec["status"] == "running" and not _alive(rec):
            rec["status"] = "lost"
        out.append(rec)
    out.sort(key=lambda r: r.get("started", ""))
    return list(reversed(out))[:n]
