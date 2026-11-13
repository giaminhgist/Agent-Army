"""Durable, supervised leaf-process jobs. No autonomous host dispatch."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import platform
import subprocess
import threading
import time
import uuid

from .errors import ArmyError
from .knowledge import project_store
from .paths import contained
from .promotions import receipt
from .store import canonical, now, sha


def file_hash(path):
    import hashlib
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            result.update(block)
    return result.hexdigest()


class Jobs:
    def __init__(self, project):
        self.root = Path(project).resolve()
        self.store = project_store(self.root)

    def _path(self, name):
        if not isinstance(name, str) or not name:
            raise ArmyError("Expected nonempty project-relative path")
        path = contained(self.root, name)
        if path.is_relative_to(self.store.root) or path == self.root:
            raise ArmyError("Job files must be outside Army state")
        return path

    def _hashes(self, names):
        return {name: file_hash(self._path(name)) for name in names}

    def create(self, spec):
        allowed = {"title", "argv", "inputs", "outputs", "seed", "device", "timeout_seconds",
                   "wall_budget_seconds", "max_attempts", "max_failures", "estimated_usd"}
        if not isinstance(spec, dict) or set(spec) - allowed:
            raise ArmyError("Unknown job specification fields")
        spec = dict(spec)
        argv = spec.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x and "\x00" not in x for x in argv):
            raise ArmyError("argv must be a nonempty string array")
        exe = Path(argv[0])
        if not exe.is_absolute() or not exe.is_file() or exe.suffix.lower() in (".bat", ".cmd"):
            raise ArmyError("Use an absolute native executable; shell scripts require a separate approved workflow")
        spec["argv"] = [str(exe.resolve()), *argv[1:]]
        if not isinstance(spec.get("title"), str) or not spec["title"].strip():
            raise ArmyError("A job title is required")
        for key, default, maximum in (("timeout_seconds", 60, 86400), ("wall_budget_seconds", 180, 259200),
                                      ("max_attempts", 3, 3), ("max_failures", 2, 2)):
            value = spec.setdefault(key, default)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ArmyError(f"Invalid {key}; maximum {maximum}")
        for key in ("inputs", "outputs"):
            values = spec.setdefault(key, [])
            if not isinstance(values, list) or len(values) > 100 or not all(isinstance(x, str) for x in values) or len(values) != len(set(values)):
                raise ArmyError(f"Invalid {key}")
            for name in values:
                self._path(name)
        if set(spec["inputs"]) & set(spec["outputs"]):
            raise ArmyError("Inputs and outputs must be separate")
        # Existing files referenced as argv arguments must be pinned too.
        for argument in argv[1:]:
            path = Path(argument)
            candidate = path if path.is_absolute() else self.root / path
            if candidate.is_file() and candidate.resolve() not in {self._path(x) for x in spec["inputs"]}:
                raise ArmyError("File arguments must be declared project inputs")
        if type(spec.get("seed")) is not int or spec.get("device") != "cpu":
            raise ArmyError("This supervised runner requires an explicit integer seed and device=cpu")
        estimate = spec.setdefault("estimated_usd", 0)
        if type(estimate) not in (float, int) or not math.isfinite(estimate) or estimate < 0:
            raise ArmyError("estimated_usd must be finite and nonnegative")
        spec["input_hashes"] = self._hashes(spec["inputs"])
        spec["executable_hash"] = file_hash(spec["argv"][0])
        task = {"id": str(uuid.uuid4()), "revision": 1, "state": "pending", "spec": spec,
                "spec_hash": sha(canonical(spec)), "attempts": [], "failures": 0,
                "wall_seconds": 0.0, "stop_requested": False, "created_at": now(), "review": None}
        with self.store.connect(True) as c:
            c.execute("CREATE TABLE IF NOT EXISTS army_jobs(id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            c.execute("INSERT INTO army_jobs VALUES(?,?)", (task["id"], canonical(task)))
            self.store.event(c, "job.created", {"id": task["id"], "spec_hash": task["spec_hash"]})
        return task

    def _get(self, c, task_id):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='army_jobs'").fetchone():
            raise ArmyError("No jobs in this project", 3)
        row = c.execute("SELECT record FROM army_jobs WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ArmyError("Unknown project job", 3)
        task = json.loads(row[0])
        if sha(canonical(task["spec"])) != task["spec_hash"]:
            raise ArmyError("Job specification integrity mismatch", 5)
        return task

    def get(self, task_id):
        with self.store.connect() as c:
            return self._get(c, task_id)

    def _save(self, c, task, action):
        task["revision"] += 1
        c.execute("UPDATE army_jobs SET record=? WHERE id=?", (canonical(task), task["id"]))
        self.store.event(c, action, {"id": task["id"], "revision": task["revision"], "state": task["state"]})

    def _verify(self, task):
        spec = task["spec"]
        if self._hashes(spec["inputs"]) != spec["input_hashes"] or file_hash(spec["argv"][0]) != spec["executable_hash"]:
            raise ArmyError("Inputs or executable changed; create a new job and obtain new consent", 4)

    def preview(self, task_id):
        task = self.get(task_id)
        self._verify(task)
        payload = {"job": task, "project": str(self.root), "mode": "supervised_leaf_process",
                   "limitations": ["No OS isolation or descendant-process containment",
                                   "Inherited environment is not a sandbox; secrets are not recorded",
                                   "USD is an estimate, not an enforced provider budget",
                                   "All argv and side effects need human inspection"]}
        return {"preview": payload, "request_hash": sha(canonical(payload))}

    def stop(self, task_id):
        with self.store.connect(True) as c:
            task = self._get(c, task_id)
            if task["state"] in ("completed", "cancelled"):
                raise ArmyError("Job is already terminal", 3)
            task["stop_requested"] = True
            if task["state"] != "running":
                task["state"] = "paused"
            self._save(c, task, "job.stop_requested")
        return task

    def run(self, task_id, authority=None, *, resume=False):
        preview = self.preview(task_id)
        task = preview["preview"]["job"]
        if task["state"] not in (("paused", "failed") if resume else ("pending",)):
            raise ArmyError("Invalid run/resume state; running jobs are never respawned automatically", 3)
        spec = task["spec"]
        remaining = spec["wall_budget_seconds"] - task["wall_seconds"]
        if len(task["attempts"]) >= spec["max_attempts"] or task["failures"] >= spec["max_failures"] or remaining <= 0:
            raise ArmyError("Job budget exhausted; create a separately approved plan", 4)
        if any(self._path(name).exists() for name in spec["outputs"]):
            raise ArmyError("Declared outputs already exist; preserve/relocate them explicitly before running", 4)
        consent = receipt(authority, "resume" if resume else "run", task_id, preview["request_hash"])
        with self.store.connect(True) as c:
            current = self._get(c, task_id)
            if current["revision"] != task["revision"]:
                raise ArmyError("Job changed during approval", 4)
            if any(json.loads(row[0])["state"] == "running" for row in c.execute("SELECT record FROM army_jobs")):
                raise ArmyError("Supervised mode permits one running job per project", 4)
            self._verify(task)
            if any(self._path(name).exists() for name in spec["outputs"]):
                raise ArmyError("Output appeared during approval", 4)
            task["state"], task["stop_requested"] = "running", False
            task["review"] = None
            attempt = {"number": len(task["attempts"]) + 1, "started_at": now(), "approval": consent,
                       "pid": None, "status": "running", "platform": platform.platform(),
                       "python": platform.python_version(), "seed": spec["seed"], "device": spec["device"]}
            task["attempts"].append(attempt)
            self._save(c, task, "job.claimed")
        # A crash after claim leaves running/unknown. Never infer success or restart.
        process = None
        started = time.monotonic()
        reason, code = "failed", None
        output = {"stdout": bytearray(), "stderr": bytearray()}
        overflow = threading.Event()
        threads = []

        def drain(stream, key):
            try:
                while block := stream.read(4096):
                    available = 1024 * 1024 - len(output[key])
                    output[key].extend(block[:max(available, 0)])
                    if len(block) > available:
                        overflow.set()
            finally:
                stream.close()

        try:
            self._verify(task)
            # Seed is made available; the program is responsible for actually using it.
            environment = dict(os.environ, ARMY_SEED=str(spec["seed"]), ARMY_DEVICE=spec["device"])
            process = subprocess.Popen(spec["argv"], cwd=self.root, env=environment, shell=False,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with self.store.connect(True) as c:
                current = self._get(c, task_id)
                current["attempts"][-1]["pid"] = process.pid
                self._save(c, current, "job.started")
            for key in output:
                thread = threading.Thread(target=drain, args=(getattr(process, key), key), daemon=True)
                thread.start()
                threads.append(thread)
            while process.poll() is None:
                if self.get(task_id)["stop_requested"]:
                    reason = "paused"
                    break
                if time.monotonic() - started >= min(spec["timeout_seconds"], remaining):
                    reason = "timeout"
                    break
                if overflow.is_set():
                    reason = "output_limit"
                    break
                time.sleep(.05)
            else:
                reason = "succeeded" if process.returncode == 0 else "failed"
        except KeyboardInterrupt:
            reason = "paused"
        except (OSError, ArmyError) as exc:
            attempt["error"] = str(exc)
            reason = "failed"
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                code = process.wait()
            for thread in threads:
                thread.join(timeout=1)
        if any(thread.is_alive() for thread in threads):
            reason = "containment_unknown"
        elif overflow.is_set():
            reason = "output_limit"
        hashes = {}
        if reason == "succeeded":
            try:
                self._verify(task)
                hashes = self._hashes(spec["outputs"])
            except (OSError, ArmyError) as exc:
                reason, attempt["error"] = "failed", str(exc)
        log_dir = contained(self.store.root, "jobs/" + task_id + "/" + str(attempt["number"]))
        log_dir.mkdir(parents=True, exist_ok=True)
        for key, value in output.items():
            contained(log_dir, key + ".log").write_bytes(bytes(value))
        with self.store.connect(True) as c:
            current = self._get(c, task_id)
            elapsed = time.monotonic() - started
            current["attempts"][-1].update({"status": reason, "ended_at": now(), "exit_code": code,
                                         "wall_seconds": elapsed, "output_hashes": hashes,
                                         "log_hashes": {k: file_hash(log_dir / (k + ".log")) for k in output},
                                         "error": attempt.get("error")})
            current["wall_seconds"] += elapsed
            current["failures"] += int(reason not in ("succeeded", "paused"))
            current["state"] = ("paused" if current["stop_requested"] or reason == "paused" else
                                "review_pending" if reason == "succeeded" else
                                "unknown" if reason == "containment_unknown" else "failed")
            self._save(c, current, "job.finished")
        return current

    def review_bundle(self, task_id):
        task = self.get(task_id)
        if task["state"] not in ("review_pending", "completed"):
            raise ArmyError("Only successful jobs can be reviewed", 3)
        self._verify(task)
        attempt = task["attempts"][-1]
        if self._hashes(task["spec"]["outputs"]) != attempt["output_hashes"]:
            raise ArmyError("Artifacts changed; review is stale", 4)
        log_dir = contained(self.store.root, "jobs/" + task_id + "/" + str(attempt["number"]))
        if {key: file_hash(contained(log_dir, key + ".log")) for key in ("stdout", "stderr")} != attempt["log_hashes"]:
            raise ArmyError("Execution logs changed; review is stale", 4)
        bundle = {"task_id": task_id, "spec_hash": task["spec_hash"], "spec": task["spec"],
                  "attempt": attempt, "reviewer_instructions": "Use a fresh context. Inspect artifacts and sources. Distinguish citation presence from claim support. No worker chat is included."}
        return {"bundle": bundle, "request_hash": sha(canonical(bundle)),
                "fresh_context_verified": False}

    def review(self, task_id, report_path, authority=None, *, preview_only=False):
        task = self.get(task_id)
        if task["state"] != "review_pending":
            raise ArmyError("Review submission requires review_pending state", 3)
        bundle = self.review_bundle(task_id)
        report_path = self._path(report_path)
        if report_path.stat().st_size > 64000:
            raise ArmyError("Review report exceeds 64k")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            raise ArmyError("Invalid review JSON") from exc
        if (not isinstance(report, dict) or set(report) != {"bundle_hash", "verdict", "findings"}
                or report["bundle_hash"] != bundle["request_hash"] or report["verdict"] not in ("pass", "fail")
                or not isinstance(report["findings"], str) or not report["findings"].strip()):
            raise ArmyError("Review must bind bundle_hash, verdict pass|fail, and nonempty findings", 4)
        review_hash = sha(canonical({"bundle": bundle["request_hash"], "report": report}))
        if preview_only:
            return {"bundle": bundle, "report": report, "request_hash": review_hash}
        consent = receipt(authority, "review", task_id, review_hash)
        with self.store.connect(True) as c:
            current = self._get(c, task_id)
            if current["revision"] != task["revision"]:
                raise ArmyError("Job changed during review approval", 4)
            self._verify(current)
            if self._hashes(current["spec"]["outputs"]) != current["attempts"][-1]["output_hashes"]:
                raise ArmyError("Review artifacts are stale", 4)
            log_dir = contained(self.store.root, "jobs/" + task_id + "/" + str(current["attempts"][-1]["number"]))
            if {key: file_hash(contained(log_dir, key + ".log")) for key in ("stdout", "stderr")} != current["attempts"][-1]["log_hashes"]:
                raise ArmyError("Review logs are stale", 4)
            current["review"] = {"report": report, "approval": consent, "review_hash": review_hash,
                                 "fresh_context_verified": False}
            current["state"] = "completed" if report["verdict"] == "pass" else "failed"
            current["failures"] += int(report["verdict"] == "fail")
            self._save(c, current, "job.reviewed")
        return current
