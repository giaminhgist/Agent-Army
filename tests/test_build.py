import copy
import tomllib
from pathlib import Path

from tests.helpers import TempHome

from army import build, config, frontmatter

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


class BuildTests(TempHome):
    def setUp(self):
        super().setUp()
        self.cfg = config.load_config(config.DEFAULT_CONFIG)

    def test_claude_agent_frontmatter(self):
        meta, body = frontmatter.parse(build.render_claude_agent("scout", self.cfg, PROMPTS))
        self.assertEqual(meta["name"], "army-scout")
        self.assertEqual(meta["model"], "sonnet")
        self.assertNotIn("skills", meta)
        self.assertIn("WebSearch", meta["tools"])
        for s in self.cfg["agents"]["scout"]["skills"]:
            self.assertIn(s, body)
        self.assertIn("## Handoff", body)
        self.assertIn("# Scout", body)
        meta, _ = frontmatter.parse(build.render_claude_agent("commander", self.cfg, PROMPTS))
        self.assertEqual(meta["model"], "fable")

    def test_codex_agent_toml_valid(self):
        d = tomllib.loads(build.render_codex_agent("scout", self.cfg, PROMPTS))
        self.assertEqual(d["name"], "army_scout")
        self.assertEqual(d["model_reasoning_effort"], "medium")
        self.assertNotIn("model", d)
        self.assertIn("research-lit", d["developer_instructions"])
        cfg = copy.deepcopy(self.cfg)
        cfg["tiers"]["codex"]["heavy"]["model"] = "my-model"
        d = tomllib.loads(build.render_codex_agent("commander", cfg, PROMPTS))
        self.assertEqual(d["model"], "my-model")
        self.assertEqual(d["model_reasoning_effort"], "xhigh")
        tricky = self.proj / "prompts"
        tricky.mkdir()
        for f in PROMPTS.glob("*.md"):
            (tricky / f.name).write_text(f.read_text())
        (tricky / "scout.md").write_text('# Scout\n"""quoted""" and \\backslash\\ and \'\'\'\n## Responsibilities\n')
        d = tomllib.loads(build.render_codex_agent("scout", self.cfg, tricky))
        self.assertIn('"""quoted""" and \\backslash\\ and \'\'\'', d["developer_instructions"])

    def test_tier_rule_per_platform(self):
        _, body = frontmatter.parse(build.render_claude_agent("commander", self.cfg, PROMPTS))
        self.assertIn("light=sonnet, medium=opus, heavy=fable", body)
        self.assertNotIn("{{TIER_RULE}}", body)
        d = tomllib.loads(build.render_codex_agent("commander", self.cfg, PROMPTS))
        self.assertIn("fixed default tier", d["developer_instructions"])
        self.assertIn("fixed default tier", build.render_skill(self.cfg, PROMPTS, "codex"))

    def test_cross_model_only_when_enabled_and_only_reviewer_auditor(self):
        self.assertNotIn("Cross-model check", build.render_claude_agent("auditor", self.cfg, PROMPTS))
        cfg = copy.deepcopy(self.cfg)
        cfg["options"]["cross_model_check"] = True
        self.assertIn("codex exec --sandbox read-only", build.render_claude_agent("auditor", cfg, PROMPTS))
        self.assertIn("codex exec --sandbox read-only", build.render_claude_agent("reviewer", cfg, PROMPTS))
        self.assertNotIn("Cross-model check", build.render_claude_agent("writer", cfg, PROMPTS))
        d = tomllib.loads(build.render_codex_agent("auditor", cfg, PROMPTS))
        self.assertIn("claude -p --permission-mode plan", d["developer_instructions"])

    def test_skill_roster(self):
        claude = build.render_skill(self.cfg, PROMPTS, "claude")
        meta, body = frontmatter.parse(claude)
        self.assertEqual(meta["name"], "army")
        self.assertIn("army-auditor", body)
        self.assertIn("army_auditor", build.render_skill(self.cfg, PROMPTS, "codex"))
        self.assertIn("get-available-resources", body)

    def test_build_all_writes_9_plus_9_plus_2(self):
        out = build.build_all(self.cfg, PROMPTS, self.proj / "build")
        self.assertEqual(len(out["claude_agents"]), 9)
        self.assertEqual(len(out["codex_agents"]), 9)
        self.assertTrue((self.proj / "build/claude/skills/army/SKILL.md").is_file())
        self.assertTrue((self.proj / "build/codex/skills/army/SKILL.md").is_file())
        self.assertTrue((self.proj / "build/claude/agents/army-commander.md").is_file())
        self.assertTrue((self.proj / "build/codex/agents/army_commander.toml").is_file())
