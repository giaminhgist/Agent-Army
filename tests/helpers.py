import os
import tempfile
import unittest
from pathlib import Path


class TempHome(unittest.TestCase):
    """Fresh HOME, ARMY_HOME and project dir per test; cwd is the project dir."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.army_home = self.home / ".agent-army"
        self.proj = root / "proj"
        self.proj.mkdir()
        self._env = {k: os.environ.get(k) for k in ("HOME", "ARMY_HOME")}
        os.environ["HOME"] = str(self.home)
        os.environ["ARMY_HOME"] = str(self.army_home)
        self._cwd = os.getcwd()
        os.chdir(self.proj)

    def tearDown(self):
        os.chdir(self._cwd)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def make_project(self, path=None):
        p = Path(path or self.proj)
        (p / ".agent-army").mkdir(parents=True, exist_ok=True)
        (p / ".agent-army" / "project.toml").write_text('name = "t"\n')
        return p
