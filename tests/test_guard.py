import tomllib

from tests.helpers import TempHome

from army import guard, project


class GuardTests(TempHome):
    RAW = ["data/raw"]

    def bash(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(self.proj)}

    def write(self, path):
        return {"tool_name": "Write", "tool_input": {"file_path": path}, "cwd": str(self.proj)}

    def check(self, payload, raw=None):
        return guard.check(payload, self.proj, self.RAW if raw is None else raw)

    def test_denied(self):
        denied = [
            self.write("data/raw/a.csv"),
            self.write(str(self.proj / "data/raw/a.csv")),
            {"tool_name": "Edit", "tool_input": {"file_path": "data/raw/a.csv"}, "cwd": str(self.proj)},
            {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": "data/raw/n.ipynb"}, "cwd": str(self.proj)},
            self.bash("rm -rf data/raw"),
            self.bash("echo x > data/raw/a.csv"),
            self.bash("echo x>>data/raw/a.csv"),
            self.bash("sed -i s/a/b/ data/raw/a.csv"),
            self.bash("mv data/raw/a.csv out/"),
            self.bash("cp x.csv data/raw/"),
            self.bash("ls && rm data/raw/a.csv"),
            self.bash("cat a | tee data/raw/b"),
            self.bash("dd if=/dev/zero of=data/raw/a.csv"),
            {"tool_name": "apply_patch", "cwd": str(self.proj),
             "tool_input": {"command": "*** Begin Patch\n*** Update File: data/raw/a.csv\n@@\n-a\n+b\n*** End Patch"}},
        ]
        for p in denied:
            r = self.check(p)
            self.assertIsNotNone(r, p)
            self.assertIn("raw data is read-only", r)

    def test_allowed(self):
        allowed = [
            self.bash("cat data/raw/a.csv"),
            self.bash("cp data/raw/a.csv derived/"),
            self.bash("python train.py --data data/raw"),
            self.bash("rsync -a data/raw/ backup/"),
            self.write("data/rawish/a.csv"),
            self.write("derived/a.csv"),
            {"tool_name": "Read", "tool_input": {"file_path": "data/raw/a.csv"}, "cwd": str(self.proj)},
        ]
        for p in allowed:
            self.assertIsNone(self.check(p), p)
        self.assertIsNone(self.check(self.bash("rm -rf data/raw"), raw=[]))

    def test_unparseable_bash_falls_back(self):
        self.assertIsNotNone(self.check(self.bash("rm 'data/raw/a.csv")))
        self.assertIsNone(self.check(self.bash("cat 'data/raw/a.csv")))

    def test_init_project_idempotent(self):
        st = project.init_project(self.proj, ["data/raw"], [])
        self.assertTrue((st / "project.toml").is_file())
        for d in ("knowledge", "memory", "runs"):
            self.assertTrue((st / d).is_dir())
        self.assertTrue((st / "plan.md").read_text().startswith("# Plan"))
        (st / "plan.md").write_text("# Plan\nmine\n")
        project.init_project(self.proj, ["data/raw", "data/ext"], ["phi"])
        cfg = tomllib.loads((st / "project.toml").read_text())
        self.assertEqual(cfg["raw_dirs"], ["data/raw", "data/ext"])
        self.assertEqual(cfg["sensitive_dirs"], ["phi"])
        self.assertEqual(cfg["name"], self.proj.name)
        project.init_project(self.proj, [], [])
        self.assertEqual(project.load_project(self.proj)["raw_dirs"], ["data/raw", "data/ext"])
        self.assertEqual((st / "plan.md").read_text(), "# Plan\nmine\n")

    def test_init_stores_relative_paths(self):
        project.init_project(self.proj, [str(self.proj / "data" / "raw")], [])
        self.assertEqual(project.load_project(self.proj)["raw_dirs"], ["data/raw"])


class InitCliTests(TempHome):
    def test_cli_init(self):
        from tests.test_promote import run_cli
        from army import paths
        code, out, _ = run_cli(["init", "--raw", "data/raw", "--sensitive", "phi"])
        self.assertEqual(code, 0)
        self.assertEqual(paths.find_project(), self.proj)
        self.assertEqual(project.load_project(self.proj)["raw_dirs"], ["data/raw"])
        self.assertIn("data/raw", out)
