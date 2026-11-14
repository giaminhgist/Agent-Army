"""Regression tests for findings of the final whole-branch review."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

from tests.helpers import TempHome
from tests.test_promote import run_cli

from army import build, config, frontmatter, guard, index, project, store

ROOT = Path(__file__).resolve().parents[1]


class ReviewFixTests(TempHome):
    def test_search_d_stroke_without_diacritics(self):
        self.make_project()
        store.add_item("project", "note", "Ghi chú", "Đường đi được để lại", project=self.proj)
        self.assertEqual(len(index.search("duong di duoc", "project", self.proj)), 1)
        self.assertEqual(len(index.search("đường", "project", self.proj)), 1)

    def test_init_refuses_global_store(self):
        with self.assertRaises(ValueError):
            project.init_project(self.home, [], [])
        os.chdir(self.home)
        code, _, err = run_cli(["init"])
        self.assertEqual(code, 2)
        self.assertIn("global store", err)
        self.assertFalse((self.army_home / "project.toml").exists())

    def test_install_py_reports_old_python(self):
        code = ("import sys; sys.modules['tomllib'] = None; sys.version_info = (3, 10, 0);"
                f"sys.argv = ['install.py']; exec(open({str(ROOT / 'install.py')!r}).read())")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("Python ≥ 3.11", r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_lock_does_not_delete_index(self):
        self.make_project()
        store.add_item("project", "note", "n", "gamma", project=self.proj)
        index.search("gamma", "project", self.proj)
        db = self.proj / ".agent-army" / "index.sqlite"
        with mock.patch("army.index.sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")):
            with self.assertRaises(sqlite3.OperationalError):
                index.search("gamma", "project", self.proj)
        self.assertTrue(db.exists())

    def test_claude_commander_points_to_skill(self):
        cfg = config.load_config(config.DEFAULT_CONFIG)
        meta, _ = frontmatter.parse(build.render_claude_agent("commander", cfg, ROOT / "prompts"))
        self.assertIn("/army", meta["description"])
        self.assertIn("claude --agent army-commander", meta["description"])


class GuardWrapperTests(TempHome):
    def check(self, cmd):
        return guard.check({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.proj)},
                           self.proj, ["data/raw"])

    def test_wrapped_and_cd_commands_denied(self):
        for cmd in ["sudo -u x rm data/raw/a", "sudo rm data/raw/a", "time rm data/raw/a", "nohup rm data/raw/a &",
                    "(rm data/raw/a)", "if true; then rm data/raw/a; fi", "echo data/raw/a | xargs rm -f",
                    "cd data/raw && rm a.csv", "cd data && rm -rf raw", "find data/raw -name '*.tmp' -delete",
                    "cp -t data/raw x.csv", "mv -t data/raw x.csv", "env A=1 rm data/raw/a"]:
            self.assertIsNotNone(self.check(cmd), cmd)

    def test_reads_still_allowed(self):
        for cmd in ["cd data/raw && ls", "find data/raw -name '*.csv'", "cd data/raw && cp a.csv ../../derived/",
                    "time python train.py --data data/raw", "sudo cat data/raw/a"]:
            self.assertIsNone(self.check(cmd), cmd)
