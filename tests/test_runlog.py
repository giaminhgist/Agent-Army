import contextlib
import io
import json
import sys

from tests.helpers import TempHome
from tests.test_promote import run_cli

from army import project, runlog, status, store


class RunlogTests(TempHome):
    def setUp(self):
        super().setUp()
        project.init_project(self.proj, [], [])

    def quiet(self, *a, **k):
        with contextlib.redirect_stdout(io.StringIO()):
            return runlog.run(*a, **k)

    def test_run_records_success_and_failure(self):
        ok = self.quiet([sys.executable, "-c", "import os;print('seed', os.environ.get('ARMY_SEED'))"],
                        self.proj, seed=7, out="out/x")
        self.assertEqual(ok["exit_code"], 0)
        self.assertEqual(ok["seed"], 7)
        self.assertEqual(ok["out"], "out/x")
        self.assertIsNone(ok["git_sha"])
        with open(ok["log"]) as fh:
            text = fh.read()
        self.assertIn("seed 7", text)
        for k in ("run_id", "cmd", "cwd", "git_sha", "git_dirty", "seed", "started", "ended", "duration_s",
                  "exit_code", "log", "out"):
            self.assertIn(k, ok)
        bad = self.quiet([sys.executable, "-c", "import sys;sys.exit(3)"], self.proj)
        self.assertEqual(bad["exit_code"], 3)
        lines = (self.proj / ".agent-army" / "runs.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        code, _, _ = run_cli(["run", "--", sys.executable, "-c", "import sys;sys.exit(3)"])
        self.assertEqual(code, 3)

    def test_run_missing_executable(self):
        r = self.quiet(["definitely-not-a-command-xyz"], self.proj)
        self.assertEqual(r["exit_code"], 127)
        self.assertEqual(len(runlog.recent(self.proj)), 1)

    def test_recent_skips_bad_lines(self):
        f = self.proj / ".agent-army" / "runs.jsonl"
        f.write_text('{"run_id": "a", "exit_code": 0, "cmd": "x"}\nnot json\n{"run_id": "b", "exit_code": 1, "cmd": "y"}\n')
        self.assertEqual([r["run_id"] for r in runlog.recent(self.proj)], ["b", "a"])

    def test_status_text_contains_sections(self):
        (self.proj / ".agent-army" / "plan.md").write_text("- [ ] write intro\n")
        self.quiet([sys.executable, "-c", "pass"], self.proj)
        store.add_item("project", "note", "n", "b", project=self.proj)
        t = status.status_text(self.proj)
        self.assertIn(self.proj.name, t)
        self.assertIn("write intro", t)
        self.assertIn("Recent runs", t)
        self.assertIn("Pending promotion: 1", t)
        code, out, _ = run_cli(["status"])
        self.assertEqual(code, 0)
        self.assertIn("Pending promotion: 1", out)
