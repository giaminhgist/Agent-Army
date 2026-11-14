"""H5: `army run -- <cmd>` runs a command and appends one provenance record to runs.jsonl."""

from __future__ import annotations

import json
import os
import secrets
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from army import paths


def _git(project: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def run(cmd: list[str], project: Path, seed: int | None = None, out: str | None = None) -> dict:
    st = paths.state_dir(project)
    (st / "runs").mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    run_id = f"{started:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"
    log_path = st / "runs" / f"{run_id}.log"
    sha = _git(project, "rev-parse", "HEAD")
    dirty = None if sha is None else bool(_git(project, "status", "--porcelain"))
    env = dict(os.environ, ARMY_RUN_ID=run_id)
    if seed is not None:
        env["ARMY_SEED"] = str(seed)
    t0 = time.monotonic()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        try:
            proc = subprocess.Popen(cmd, cwd=Path.cwd(), env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors="replace")
        except OSError as e:
            msg = f"army run: cannot start {cmd[0] if cmd else ''}: {e}\n"
            sys.stderr.write(msg)
            log.write(msg)
            code = 127
        else:
            with proc.stdout:
                for line in proc.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log.write(line)
            code = proc.wait()
    rec = {
        "run_id": run_id, "cmd": shlex.join(cmd), "cwd": str(Path.cwd()), "git_sha": sha, "git_dirty": dirty,
        "seed": seed, "started": started.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "ended": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_s": round(time.monotonic() - t0, 3), "exit_code": code, "log": str(log_path), "out": out,
    }
    with open(st / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def recent(project: Path, n: int = 5) -> list[dict]:
    f = paths.state_dir(project) / "runs.jsonl"
    if not f.is_file():
        return []
    out = []
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return list(reversed(out))[:n]
