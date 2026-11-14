import contextlib
import io
import json
import os

from tests.helpers import TempHome

from army import frontmatter, install

MARK = "<!-- agent-army:start -->"


class InstallTests(TempHome):
    def setUp(self):
        super().setUp()
        (self.home / ".claude").mkdir()
        (self.home / ".codex").mkdir()
        self.settings = self.home / ".claude/settings.json"
        self.settings.write_text(json.dumps({
            "theme": "dark",
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo user-hook"}]}]}}))
        (self.home / ".claude/CLAUDE.md").write_text("# my rules\n")

    def inst(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = install.main(list(args))
        return code, out.getvalue()

    def army_groups(self, path, event):
        data = json.loads(path.read_text())
        return [g for g in data["hooks"].get(event, [])
                if any("/.agent-army/bin/army hook" in h["command"] for h in g["hooks"])]

    def test_install_both_platforms_layout(self):
        code, _ = self.inst("--claude", "--codex")
        self.assertEqual(code, 0)
        self.assertEqual(len(list((self.home / ".claude/agents").glob("army-*.md"))), 9)
        self.assertEqual(len(list((self.home / ".codex/agents").glob("army_*.toml"))), 9)
        self.assertTrue((self.home / ".claude/skills/army/SKILL.md").is_file())
        self.assertTrue((self.home / ".agents/skills/army/SKILL.md").is_file())
        launcher = self.army_home / "bin/army"
        self.assertTrue(os.access(launcher, os.X_OK))
        self.assertTrue((self.home / ".local/bin/army").is_symlink())
        man = json.loads((self.army_home / "install-manifest.json").read_text())
        self.assertEqual(man["platforms"], ["claude", "codex"])
        self.assertTrue((self.army_home / "army.toml").is_file())
        codex_hooks = self.home / ".codex/hooks.json"
        for ev in ("SessionStart", "Stop", "PreToolUse", "PreCompact"):
            self.assertEqual(len(self.army_groups(self.settings, ev)), 1, ev)
            self.assertEqual(len(self.army_groups(codex_hooks, ev)), 1, ev)
        self.assertEqual(self.army_groups(codex_hooks, "PreToolUse")[0]["matcher"], "Bash|apply_patch")
        self.assertIn(MARK, (self.home / ".codex/AGENTS.md").read_text())

    def test_install_is_idempotent_and_keeps_user_config(self):
        self.inst("--claude", "--codex")
        user_cfg = self.army_home / "army.toml"
        user_cfg.write_text(user_cfg.read_text().replace(
            '[agents.scout]\ntier = "light"', '[agents.scout]\ntier = "medium"'))
        self.inst("--claude", "--codex")
        self.assertIn('[agents.scout]\ntier = "medium"', user_cfg.read_text())
        for ev in ("SessionStart", "Stop", "PreToolUse", "PreCompact"):
            self.assertEqual(len(self.army_groups(self.settings, ev)), 1, ev)
        data = json.loads(self.settings.read_text())
        self.assertEqual(data["theme"], "dark")
        self.assertTrue(any(h["command"] == "echo user-hook" for g in data["hooks"]["Stop"] for h in g["hooks"]))
        cm = (self.home / ".claude/CLAUDE.md").read_text()
        self.assertEqual(cm.count(MARK), 1)
        self.assertTrue(cm.startswith("# my rules\n"))
        meta, _ = frontmatter.parse((self.home / ".claude/agents/army-scout.md").read_text())
        self.assertEqual(meta["model"], "opus")
        user_cfg.write_text(user_cfg.read_text().replace(
            '[agents.scout]\ntier = "medium"', '[agents.scout]\ntier = "heavy"'))
        install.redeploy()
        meta, _ = frontmatter.parse((self.home / ".claude/agents/army-scout.md").read_text())
        self.assertEqual(meta["model"], "fable")

    def test_uninstall_restores(self):
        self.inst("--claude", "--codex")
        (self.army_home / "knowledge" / "keep.md").write_text("x")
        code, _ = self.inst("--uninstall")
        self.assertEqual(code, 0)
        self.assertEqual(list((self.home / ".claude/agents").glob("army-*")), [])
        self.assertEqual(list((self.home / ".codex/agents").glob("army_*")), [])
        self.assertFalse((self.home / ".claude/skills/army").exists())
        self.assertFalse((self.home / ".local/bin/army").exists())
        self.assertNotIn("agent-army", self.settings.read_text())
        self.assertEqual(json.loads(self.settings.read_text())["theme"], "dark")
        self.assertNotIn(MARK, (self.home / ".claude/CLAUDE.md").read_text())
        self.assertTrue((self.army_home / "knowledge" / "keep.md").is_file())
        self.assertFalse((self.army_home / "app").exists())
        self.inst("--claude")
        self.inst("--uninstall", "--purge")
        self.assertFalse(self.army_home.exists())

    def test_dry_run_writes_nothing(self):
        before = sorted(p.relative_to(self.home) for p in self.home.rglob("*"))
        code, out = self.inst("--claude", "--codex", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("dry-run", out)
        self.assertEqual(sorted(p.relative_to(self.home) for p in self.home.rglob("*")), before)
