from tests import helpers  # noqa: F401  (sets sys.path)
from tests.helpers import TempHome

from army import config, frontmatter, paths

ORDER = ["commander", "scout", "strategist", "engineer", "experimenter",
         "writer", "editor", "reviewer", "auditor"]


class CoreTests(TempHome):
    def test_frontmatter_roundtrip(self):
        meta = {"id": "a", "tags": ["x", "y"], "n": 3, "ok": True, "title": "a: b"}
        text = frontmatter.dump(meta, "body\nline")
        m, body = frontmatter.parse(text)
        self.assertEqual(m, meta)
        self.assertEqual(body, "body\nline")

    def test_config_has_nine_agents_with_ten_skills(self):
        cfg = config.load_config()
        self.assertEqual(config.agent_names(cfg), ORDER)
        for name in ORDER:
            self.assertEqual(len(cfg["agents"][name]["skills"]), 10, name)

    def test_tier_for(self):
        cfg = config.load_config()
        self.assertEqual(config.tier_for(cfg, "scout", "claude"), {"model": "sonnet", "effort": None})
        self.assertEqual(config.tier_for(cfg, "commander", "claude"), {"model": "fable", "effort": None})
        self.assertEqual(config.tier_for(cfg, "auditor", "codex"), {"model": None, "effort": "high"})

    def test_find_project(self):
        self.make_project()
        deep = self.proj / "a" / "b"
        deep.mkdir(parents=True)
        self.assertEqual(paths.find_project(deep), self.proj)

    def test_home_store_is_not_a_project(self):
        self.army_home.mkdir()
        (self.army_home / "project.toml").write_text('name = "x"\n')
        sub = self.home / "x"
        sub.mkdir()
        self.assertIsNone(paths.find_project(sub))

    def test_scope_dir(self):
        self.assertEqual(paths.scope_dir("global", None), self.army_home)
        self.assertEqual(paths.scope_dir("project", self.proj), self.proj / ".agent-army")
        with self.assertRaises(ValueError):
            paths.scope_dir("project", None)
