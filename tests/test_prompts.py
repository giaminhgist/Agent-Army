import re
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401

from army import config

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


class PromptTests(unittest.TestCase):
    def test_prompts_complete(self):
        cfg = config.load_config(config.DEFAULT_CONFIG)
        for name in config.agent_names(cfg):
            text = (PROMPTS / f"{name}.md").read_text()
            self.assertIn("## Responsibilities", text, name)
            self.assertIn("## Working method", text, name)
            self.assertIn("## Do not", text, name)
        proto = (PROMPTS / "_protocol.md").read_text()
        self.assertIn("## Handoff", proto)
        self.assertIn("army kb search", proto)
        self.assertIn("army run", proto)
        self.assertIn("Status: completed | partial | blocked", proto)
        self.assertIn("Verdict: accept | repair | reject", (PROMPTS / "auditor.md").read_text())
        self.assertIn("{{TIER_RULE}}", (PROMPTS / "commander.md").read_text())
        for f in PROMPTS.glob("*.md"):
            self.assertIsNone(re.search(r"\[(SOURCED|RUN|INFERRED|HYPOTHESIS)", f.read_text()), f.name)
