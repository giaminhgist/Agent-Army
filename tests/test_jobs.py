import contextlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from agent_army.approvals import ConsoleAuthority
from agent_army.cli import main
from agent_army.errors import ArmyError
from agent_army.jobs import Jobs
from agent_army.knowledge import initialize_project
from agent_army.promotions import receipt


class Authority:
    def authorize(self, action, target_id, request_hash):
        return {"action": action, "target_id": target_id, "request_hash": request_hash,
                "actor_id": "test-only", "receipt_id": "test-receipt",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        initialize_project(self.root)
        self.jobs = Jobs(self.root)
        self.authority = Authority()

    def create(self, code="print('ok')", **updates):
        (self.root / "work.py").write_text(code, encoding="utf-8")
        spec = {"title": "Synthetic CPU fixture", "argv": [sys.executable, "work.py"],
                "inputs": ["work.py"], "outputs": [], "seed": 42, "device": "cpu"}
        spec.update(updates)
        return self.jobs.create(spec)

    def test_default_no_authority_no_spawn(self):
        task = self.create()
        with patch("agent_army.jobs.subprocess.Popen") as spawn, self.assertRaises(ArmyError):
            self.jobs.run(task["id"])
        spawn.assert_not_called()
        self.assertEqual(self.jobs.get(task["id"])["state"], "pending")

    def test_cli_default_no_approval(self):
        task = self.create()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(["--isolated", "--project", str(self.root), "job", "run", task["id"], "--json"])
        self.assertEqual(code, 4)
        self.assertFalse(json.loads(out.getvalue())["ok"])

    def test_success_review_and_stale_artifacts(self):
        task = self.create("from pathlib import Path\nimport os\nPath('result.txt').write_text(os.environ['ARMY_SEED'])", outputs=["result.txt"])
        done = self.jobs.run(task["id"], self.authority)
        self.assertEqual(done["state"], "review_pending")
        self.assertEqual((self.root / "result.txt").read_text(), "42")
        bundle = self.jobs.review_bundle(task["id"])
        report = {"bundle_hash": bundle["request_hash"], "verdict": "pass", "findings": "Seed output verified"}
        (self.root / "review.json").write_text(json.dumps(report))
        with self.assertRaises(ArmyError):
            self.jobs.review(task["id"], "review.json")
        final = self.jobs.review(task["id"], "review.json", self.authority)
        self.assertEqual(final["state"], "completed")
        self.assertFalse(final["review"]["fresh_context_verified"])
        (self.root / "result.txt").write_text("tampered")
        with self.assertRaises(ArmyError):
            self.jobs.review_bundle(task["id"])

    def test_existing_output_is_not_new_evidence(self):
        task = self.create(outputs=["old.txt"])
        (self.root / "old.txt").write_text("old")
        with self.assertRaises(ArmyError):
            self.jobs.run(task["id"], self.authority)

    def test_changed_input_blocks(self):
        task = self.create()
        (self.root / "work.py").write_text("print('changed')")
        with self.assertRaises(ArmyError):
            self.jobs.run(task["id"], self.authority)

    def test_missing_output_fails(self):
        task = self.create(outputs=["absent.txt"])
        self.assertEqual(self.jobs.run(task["id"], self.authority)["state"], "failed")

    def test_failed_retries_bounded(self):
        task = self.create("raise SystemExit(2)")
        self.assertEqual(self.jobs.run(task["id"], self.authority)["failures"], 1)
        self.assertEqual(self.jobs.run(task["id"], self.authority, resume=True)["failures"], 2)
        with self.assertRaises(ArmyError):
            self.jobs.run(task["id"], self.authority, resume=True)

    def test_timeout(self):
        task = self.create("import time; time.sleep(5)", timeout_seconds=1)
        result = self.jobs.run(task["id"], self.authority)
        self.assertEqual(result["attempts"][-1]["status"], "timeout")
        self.assertLess(result["wall_seconds"], 4)

    def test_stop_and_resume(self):
        task = self.create()
        self.assertEqual(self.jobs.stop(task["id"])["state"], "paused")
        with self.assertRaises(ArmyError):
            self.jobs.run(task["id"], self.authority)
        self.assertEqual(self.jobs.run(task["id"], self.authority, resume=True)["state"], "review_pending")

    def test_running_stop_and_no_duplicate(self):
        task = self.create("import time; time.sleep(4)")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.jobs.run, task["id"], self.authority)
            deadline = time.monotonic() + 5
            while self.jobs.get(task["id"])["state"] != "running":
                if time.monotonic() > deadline:
                    self.fail("Runner did not claim job")
                time.sleep(.02)
            with self.assertRaises(ArmyError):
                self.jobs.run(task["id"], self.authority)
            self.jobs.stop(task["id"])
            self.assertEqual(future.result(timeout=5)["state"], "paused")

    def test_expired_mismatched_receipts(self):
        task = self.create()
        for field, value in (("expires_at", "2000-01-01T00:00:00+00:00"), ("request_hash", "other")):
            real = self.authority.authorize
            class Bad:
                def authorize(self, *args):
                    result = real(*args)
                    result[field] = value
                    return result
            with self.assertRaises(ArmyError):
                self.jobs.run(task["id"], Bad())

    def test_stop_during_consent_invalidates(self):
        task = self.create()
        real = self.authority.authorize
        jobs = self.jobs
        class Racing:
            def authorize(self, *args):
                jobs.stop(task["id"])
                return real(*args)
        with self.assertRaises(ArmyError):
            self.jobs.run(task["id"], Racing())

    def test_output_limit(self):
        task = self.create("import sys; sys.stdout.write('x'*2000000)")
        result = self.jobs.run(task["id"], self.authority)
        self.assertEqual(result["attempts"][-1]["status"], "output_limit")
        log = self.root / ".agent-army/jobs" / task["id"] / "1/stdout.log"
        self.assertEqual(log.stat().st_size, 1024 * 1024)

    def test_path_and_budget_validation(self):
        for updates in ({"outputs": ["../escape"]}, {"max_attempts": 4}, {"max_failures": 3},
                        {"device": "gpu"}, {"inputs": []}, {"estimated_usd": float("nan")},
                        {"outputs": [".agent-army/owned"]}):
            with self.assertRaises(ArmyError):
                self.create(**updates)

    def test_crashed_claim_never_respawns(self):
        task = self.create()
        with self.jobs.store.connect(True) as c:
            task["state"] = "running"
            self.jobs._save(c, task, "fixture.crashed")
        with patch("agent_army.jobs.subprocess.Popen") as spawn, self.assertRaises(ArmyError):
            self.jobs.run(task["id"], self.authority, resume=True)
        spawn.assert_not_called()

    def test_console_rejects_pipe(self):
        with patch("sys.stdin", io.StringIO("yes\n")), self.assertRaises(ArmyError):
            ConsoleAuthority("run", "id", "hash", {}).authorize("run", "id", "hash")

    def test_console_exact_scope_and_one_use(self):
        class TTY(io.StringIO):
            def isatty(self):
                return True
        authority = ConsoleAuthority("run", "id", "hash", {"text": "\x1b[2J"})
        with patch("sys.stdin", TTY("abcd\n")), patch("sys.stderr", TTY()) as out, patch("secrets.token_hex", return_value="abcd"):
            receipt(authority, "run", "id", "hash")
            self.assertIn("\\u001b", out.getvalue())
            with self.assertRaises(ArmyError):
                receipt(authority, "run", "id", "hash")

    def test_review_fail_counts_towards_budget(self):
        task = self.create()
        self.jobs.run(task["id"], self.authority)
        bundle = self.jobs.review_bundle(task["id"])
        (self.root / "review.json").write_text(json.dumps({"bundle_hash": bundle["request_hash"], "verdict": "fail", "findings": "Evidence missing"}))
        result = self.jobs.review(task["id"], "review.json", self.authority)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["failures"], 1)

    def test_logs_tamper_invalidates_bundle(self):
        task = self.create()
        self.jobs.run(task["id"], self.authority)
        (self.root / ".agent-army/jobs" / task["id"] / "1/stdout.log").write_text("changed")
        with self.assertRaises(ArmyError):
            self.jobs.review_bundle(task["id"])

    def test_attempt_and_wall_caps(self):
        for key, value in (("wall_seconds", 180), ("attempts", [{}, {}, {}])):
            task = self.create()
            task[key], task["state"] = value, "paused"
            with self.jobs.store.connect(True) as c:
                self.jobs._save(c, task, "fixture.budget")
            with self.assertRaises(ArmyError):
                self.jobs.run(task["id"], self.authority, resume=True)

    def test_input_changed_during_approval(self):
        task = self.create()
        root, real = self.root, self.authority.authorize
        class Racing:
            def authorize(self, *args):
                (root / "work.py").write_text("print('changed')")
                return real(*args)
        with patch("agent_army.jobs.subprocess.Popen") as spawn, self.assertRaises(ArmyError):
            self.jobs.run(task["id"], Racing())
        spawn.assert_not_called()

    def test_review_output_changed_during_consent(self):
        task = self.create("from pathlib import Path; Path('out.txt').write_text('result')", outputs=["out.txt"])
        self.jobs.run(task["id"], self.authority)
        bundle = self.jobs.review_bundle(task["id"])
        (self.root / "review.json").write_text(json.dumps({"bundle_hash": bundle["request_hash"], "verdict": "pass", "findings": "checked"}))
        root, real = self.root, self.authority.authorize
        class Racing:
            def authorize(self, *args):
                (root / "out.txt").write_text("changed")
                return real(*args)
        with self.assertRaises(ArmyError):
            self.jobs.review(task["id"], "review.json", Racing())

    def test_console_denial_and_wrong_scope(self):
        class TTY(io.StringIO):
            def isatty(self):
                return True
        authority = ConsoleAuthority("run", "id", "hash", {})
        with self.assertRaises(ArmyError):
            authority.authorize("publish", "id", "hash")
        with patch("sys.stdin", TTY("\n")), patch("sys.stderr", TTY()), self.assertRaises(ArmyError):
            authority.authorize("run", "id", "hash")

    def test_cli_console_promotion_publish_revoke_fixture(self):
        from agent_army.knowledge import Knowledge
        from agent_army.store import Store
        from agent_army.promotions import Promotions
        class TTY(io.StringIO):
            def isatty(self):
                return True
        with tempfile.TemporaryDirectory() as global_dir, patch.dict("os.environ", {"AGENT_ARMY_HOME": global_dir}):
            Store.initialize(Path(global_dir), "global")
            knowledge = Knowledge(self.root)
            item = knowledge.project.add("memory", "fixture", "public fixture")
            proposal = Promotions(knowledge).prepare(item["id"])
            for action in ("publish", "revoke"):
                with patch("sys.stdin", TTY("abcd\n")), patch("sys.stderr", TTY()), patch("secrets.token_hex", return_value="abcd"), contextlib.redirect_stdout(io.StringIO()) as out:
                    code = main(["--isolated", "--project", str(self.root), "promotion", action, proposal["id"], "--console", "--json"])
                self.assertEqual(code, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
