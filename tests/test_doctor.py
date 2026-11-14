import json

from tests.helpers import TempHome
from tests.test_promote import run_cli

from army import doctor


def mkskill(root, name):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n")


class DoctorTests(TempHome):
    def test_find_skill_bare_and_plugin_cache(self):
        mkskill(self.home / ".claude/skills", "arxiv")
        mkskill(self.home / ".claude/plugins/cache/mk/superpowers/7.0.2/skills", "brainstorming")
        mkskill(self.home / ".agents/skills", "humanizer")
        mkskill(self.home / ".codex/plugins/cache/x/y/1/skills", "research-lit")
        self.assertIsNotNone(doctor.find_skill("arxiv", "claude"))
        self.assertIsNotNone(doctor.find_skill("brainstorming", "claude"))
        self.assertIsNone(doctor.find_skill("humanizer", "claude"))
        self.assertIsNotNone(doctor.find_skill("humanizer", "codex"))
        self.assertIsNotNone(doctor.find_skill("research-lit", "codex"))
        self.assertIsNone(doctor.find_skill("arxiv", "codex"))

    def test_missing_skills_warn_not_fail(self):
        self.army_home.mkdir()
        checks = doctor.run_checks(["claude"])
        miss = [c for c in checks if c.name.startswith("recommended skills")]
        self.assertEqual(len(miss), 1)
        self.assertEqual(miss[0].status, "WARN")
        self.assertIn("humanizer (editor)", miss[0].detail)
        agents = [c for c in checks if c.name == "claude agents"][0]
        self.assertEqual(agents.status, "FAIL")

    def test_doctor_exit_code(self):
        self.army_home.mkdir()
        code, out, _ = run_cli(["doctor"])
        self.assertEqual(code, 0)
        self.assertIn("[OK]", out)
        (self.army_home / "install-manifest.json").write_text(json.dumps({"platforms": ["codex"]}))
        code, out, _ = run_cli(["doctor"])
        self.assertEqual(code, 1)
        self.assertIn("[FAIL]", out)
        self.assertIn("/hooks", out)
