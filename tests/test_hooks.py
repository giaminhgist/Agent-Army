import json

from tests.helpers import TempHome

from army import hooks, project, promote, store


class HookTests(TempHome):
    def setUp(self):
        super().setUp()
        project.init_project(self.proj, ["data/raw"], [])

    def payload(self, **kw):
        d = {"cwd": str(self.proj), "session_id": "s", "hook_event_name": "x"}
        d.update(kw)
        return json.dumps(d)

    def test_session_start_outputs_brief(self):
        store.add_item("project", "decision", "Use subject-level CV", "", project=self.proj)
        for platform in ("claude", "codex"):
            code, out, err = hooks.handle("session-start", platform, self.payload())
            self.assertEqual(code, 0)
            self.assertIn("Recent decisions", out)

    def test_session_start_no_project_no_global_is_silent(self):
        code, out, _ = hooks.handle("session-start", "claude", json.dumps({"cwd": str(self.home)}))
        self.assertEqual((code, out), (0, ""))

    def test_stop_notifies_only_on_increase(self):
        def stop():
            return hooks.handle("stop", "claude", self.payload())
        a = store.add_item("project", "note", "a", "", project=self.proj)
        code, out, _ = stop()
        self.assertEqual(code, 0)
        msg = json.loads(out)
        self.assertEqual(set(msg), {"systemMessage"})
        self.assertIn("1 item(s) pending promotion", msg["systemMessage"])
        self.assertEqual(stop()[1], "")
        store.add_item("project", "note", "b", "", project=self.proj)
        self.assertIn("2 item(s)", json.loads(stop()[1])["systemMessage"])
        promote.promote([i.id for i in promote.pending(self.proj)], self.proj)
        self.assertEqual(stop()[1], "")
        store.add_item("project", "note", "c", "", project=self.proj)
        self.assertIn("1 item(s)", json.loads(stop()[1])["systemMessage"])

    def test_pre_tool_use_denies_raw_write(self):
        p = self.payload(tool_name="Write", tool_input={"file_path": "data/raw/x.csv"})
        code, out, err = hooks.handle("pre-tool-use", "claude", p)
        self.assertEqual(code, 2)
        self.assertIn("raw data is read-only", err)
        p = self.payload(tool_name="Bash", tool_input={"command": "ls data/raw"})
        self.assertEqual(hooks.handle("pre-tool-use", "codex", p), (0, "", ""))

    def test_pre_compact_writes_snapshot_and_brief_includes_it(self):
        (self.proj / ".agent-army" / "plan.md").write_text("- [ ] train baseline\n")
        code, out, _ = hooks.handle("pre-compact", "claude", self.payload())
        self.assertEqual((code, out), (0, ""))
        snap = (self.proj / ".agent-army" / "snapshot.md").read_text()
        self.assertTrue(snap.startswith("# Snapshot "))
        self.assertIn("train baseline", snap)
        _, out, _ = hooks.handle("session-start", "claude", self.payload())
        self.assertIn("# Snapshot", out)

    def test_hooks_fail_open(self):
        log = self.army_home / "hook-errors.log"
        cases = [("session-start", "not json")]
        bad = self.proj.parent / "bad"
        (bad / ".agent-army").mkdir(parents=True)
        (bad / ".agent-army" / "project.toml").write_text("this is = = not toml")
        cases.append(("pre-tool-use", json.dumps({"cwd": str(bad), "tool_name": "Write",
                                                   "tool_input": {"file_path": "x"}})))
        for event, stdin in cases:
            code, out, _ = hooks.handle(event, "claude", stdin)
            self.assertEqual(code, 0, event)
            self.assertEqual(out, "")
        self.assertTrue(log.is_file())
        n = len(log.read_text())
        store.add_item("project", "note", "n", "", project=self.proj)
        (self.proj / ".agent-army" / "index.sqlite").write_bytes(b"junk" * 50)
        code, _, _ = hooks.handle("session-start", "claude", self.payload())
        self.assertEqual(code, 0)
        self.assertEqual(hooks.handle("nonsense", "claude", self.payload()), (0, "", ""))
        self.assertGreaterEqual(len(log.read_text()), n)
