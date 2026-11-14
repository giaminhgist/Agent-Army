import contextlib
import io
import json
import os
import subprocess
import sys

from tests.helpers import TempHome

from army import install


class E2ETests(TempHome):
    def army(self, *args, stdin=""):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        return subprocess.run([str(self.army_home / "bin/army"), *args], input=stdin, capture_output=True,
                              text=True, cwd=self.proj, env=env, timeout=60)

    def test_e2e_cli_flow(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(install.main(["--claude", "--codex"]), 0)
        r = self.army("init", "--raw", "data/raw")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.army("kb", "add", "--type", "note", "--title", "Fixation entropy", stdin="fixation entropy predicts MCI")
        self.assertEqual(r.returncode, 0, r.stderr)
        item_id = r.stdout.strip()
        r = self.army("kb", "search", "entropy")
        self.assertIn(item_id, r.stdout)
        self.assertEqual(self.army("mem", "add", "Use subject-level CV", "--kind", "decision").returncode, 0)
        r = self.army("run", "--", sys.executable, "-c", "print(42)")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("42", r.stdout)
        self.assertIn("run_id=", r.stderr)
        r = self.army("status")
        self.assertIn("Recent runs:", r.stdout)
        r = self.army("hook", "session-start", "--platform", "codex", stdin=json.dumps({"cwd": str(self.proj)}))
        self.assertEqual(r.returncode, 0)
        self.assertIn("Recent decisions", r.stdout)
        r = self.army("hook", "pre-tool-use", "--platform", "claude", stdin=json.dumps(
            {"cwd": str(self.proj), "tool_name": "Write", "tool_input": {"file_path": "data/raw/x"}}))
        self.assertEqual(r.returncode, 2)
        self.assertIn("read-only", r.stderr)
        self.assertEqual(self.army("promote", item_id).returncode, 0)
        r = self.army("kb", "search", "entropy", "--scope", "global")
        self.assertIn(item_id, r.stdout)
        r = self.army("build")
        self.assertEqual(r.returncode, 0, r.stderr)
