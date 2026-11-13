import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_army.cli import main
from agent_army.config import load_layers
from agent_army.errors import ArmyError
from agent_army.registry import Registry
from agent_army.skills.discovery import SkillRoot, claude_plugin_roots, default_roots, discover
from agent_army.skills.metadata import parse_header
from agent_army.skills.resolver import resolve_skills


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = Registry()

    def write_skill(self, folder, name="custom-literature", description="search literature evidence",
                    extra="", origin="independent-source"):
        path = self.root / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(
            "---\nname: " + name + "\ndescription: " + description + "\n" + extra +
            "---\n# Instructions\nDo not execute this during discovery.\n", encoding="utf-8")
        return SkillRoot(path, origin)

    def inventory(self, roots, **kwargs):
        return discover(roots, "codex", env={}, which=lambda _: None, **kwargs)

    def resolve(self, inventory, task="search literature evidence", **kwargs):
        return resolve_skills(inventory, self.registry, "research", task, **kwargs)

    def test_multiline_yaml_bom_and_unknown_fields(self):
        data = parse_header("\ufeff---\nname: sample\ndescription: |\n  first line\n  second line\nallowed-tools: Read\n---\nbody")
        self.assertIn("second line", data["description"])
        self.assertEqual(data["allowed-tools"], "Read")

    def test_duplicate_unsafe_alias_and_missing_header(self):
        for text in ("---\nname: a\nname: b\n---", "---\nname: !!python/object:bad {}\n---",
                     "---\nname: &x abc\ndescription: *x\n---", "plain text",
                     "---\nname: x", "---\n- a\n- b\n---"):
            with self.subTest(text=text), self.assertRaises(ArmyError):
                parse_header(text)

    def test_third_party_without_catalog_for_all_agents(self):
        root = self.write_skill("external")
        inventory = self.inventory([root])
        for agent in self.registry.agents:
            result = resolve_skills(inventory, self.registry, agent, "search literature evidence")
            self.assertEqual(result["fallback_mode"], "skills")
            self.assertEqual(result["selected"][0]["name"], "custom-literature")

    def test_external_more_relevant_than_suggestion(self):
        suggested = self.write_skill("recommended", "literature-review", "literature",
                                     origin="https://github.com/k-dense-ai/scientific-agent-skills")
        external = self.write_skill("external", "custom-review", "search literature evidence systematic synthesis")
        result = self.resolve(self.inventory([suggested, external]), max_selected=1)
        self.assertEqual(result["selected"][0]["name"], "custom-review")

    def test_empty_roots_and_tool_fallback(self):
        inventory = self.inventory([])
        self.assertEqual(self.resolve(inventory)["fallback_mode"], "tools")
        blocked = self.resolve(inventory, required=["paper-search"])
        self.assertEqual(blocked["fallback_mode"], "blocked")
        self.assertEqual(blocked["missing_capabilities"], ["paper-search"])
        tools = self.resolve(inventory, required=["paper-search"], tool_capabilities=["paper-search"])
        self.assertEqual(tools["fallback_mode"], "tools")

    def test_unknown_requirements_not_declared_ready(self):
        inventory = self.inventory([self.write_skill("unknown")])
        self.assertEqual(inventory["skills"][0]["eligibility"], "unknown")
        result = self.resolve(inventory)
        self.assertEqual(result["selected"][0]["eligibility"], "unknown")
        self.assertFalse(result["execution_authorized"])

    def test_declared_dependencies_and_env_tools(self):
        extra = "metadata:\n  army:\n    dependencies: []\n    requires_env: [PRIVATE_TEST_KEY]\n    requires_tools: [imaginary-tool]\n"
        root = self.write_skill("requirements", extra=extra)
        bad = self.inventory([root])
        self.assertEqual(bad["skills"][0]["eligibility"], "unavailable")
        good = discover([root], "codex", env={"PRIVATE_TEST_KEY": "SECRET-NOT-FOR-OUTPUT"}, which=lambda _: "/tool")
        self.assertEqual(good["skills"][0]["eligibility"], "declared_ready")
        self.assertNotIn("SECRET-NOT-FOR-OUTPUT", json.dumps(good))
        self.assertEqual(self.resolve(bad)["fallback_mode"], "tools")

    def test_disabled_and_incompatible(self):
        disabled = self.write_skill("disabled", extra="metadata:\n  army:\n    enabled: false\n")
        incompatible = self.write_skill("claude", extra="metadata:\n  army:\n    hosts: [claude]\n")
        result = self.resolve(self.inventory([disabled, incompatible]))
        self.assertFalse(result["selected"])
        self.assertEqual(len(result["unavailable"]), 2)

    def test_collision_requires_exact_id(self):
        one = self.write_skill("one", "same-name")
        two = self.write_skill("two", "same-name")
        inventory = self.inventory([one, two])
        result = self.resolve(inventory, pinned=["same-name"])
        self.assertFalse(result["selected"])
        self.assertTrue(result["ambiguous"])
        sid = inventory["skills"][0]["id"]
        exact = self.resolve(inventory, pinned=[sid], max_selected=1)
        self.assertEqual(exact["selected"][0]["id"], sid)

    def test_dependency_missing_cycle_and_dedup(self):
        a = self.write_skill("a", "a", extra="metadata:\n  army:\n    dependencies: [missing]\n")
        self.assertIn("missing", self.resolve(self.inventory([a]))["unavailable"][0]["reason"])
        a = self.write_skill("a", "a", extra="metadata:\n  army:\n    dependencies: [b]\n")
        b = self.write_skill("b", "b", "helper only", extra="metadata:\n  army:\n    dependencies: [a]\n")
        self.assertIn("cycle", self.resolve(self.inventory([a, b]))["unavailable"][0]["reason"])
        b = self.write_skill("b", "b", "helper only")
        a = self.write_skill("a", "a", extra="metadata:\n  army:\n    dependencies: [b, b]\n")
        result = self.resolve(self.inventory([a, b]))
        self.assertEqual([d["name"] for d in result["dependencies"]], ["b"])

    def test_ambiguous_dependency_rejected(self):
        a = self.write_skill("a", "a", extra="metadata:\n  army:\n    dependencies: [helper]\n")
        b = self.write_skill("b", "helper", "helper only")
        c = self.write_skill("c", "helper", "helper only")
        result = self.resolve(self.inventory([a, b, c]))
        self.assertFalse(result["selected"])
        self.assertTrue(result["ambiguous"])

    def test_manual_only_requires_pin(self):
        root = self.write_skill("manual", extra="disable-model-invocation: true\n")
        inventory = self.inventory([root])
        self.assertFalse(self.resolve(inventory)["selected"])
        self.assertEqual(len(self.resolve(inventory, pinned=["custom-literature"])["selected"]), 1)

    def test_refresh_detects_edit_and_removal(self):
        root = self.write_skill("refresh")
        first = self.inventory([root])["skills"][0]
        path = root.path / "SKILL.md"
        path.write_text(path.read_text() + "\nChanged body\n")
        second = self.inventory([root])["skills"][0]
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(first["content_hash"], second["content_hash"])
        path.unlink()
        self.assertEqual(self.inventory([root])["skills"], [])

    def test_overlap_roots_dedup_and_bad_file_diagnostics(self):
        root = self.write_skill("nested/valid")
        invalid = self.root / "nested/invalid"
        invalid.mkdir()
        (invalid / "SKILL.md").write_text("---\nname: x\n---\n")
        parent = SkillRoot(self.root / "nested", "parent")
        inventory = self.inventory([parent, root])
        self.assertEqual(len(inventory["skills"]), 1)
        self.assertTrue(inventory["diagnostics"])

    def test_overrides_do_not_change_source_and_validate(self):
        root = self.write_skill("override")
        path = str((root.path / "SKILL.md").resolve())
        before = Path(path).read_bytes()
        inventory = self.inventory([root], overrides={path: {"capabilities": ["special"], "enabled": False}})
        self.assertEqual(inventory["skills"][0]["capabilities"], ["special"])
        self.assertEqual(inventory["skills"][0]["eligibility"], "unavailable")
        self.assertEqual(Path(path).read_bytes(), before)
        with self.assertRaises(ArmyError):
            self.inventory([root], overrides={path: {"unknown": True}})

    def test_root_bounds_and_no_script_execution(self):
        root = self.write_skill("registered")
        (root.path / "run.py").write_text("raise RuntimeError('MUST NOT EXECUTE')")
        self.write_skill("outside", "outside")
        inventory = self.inventory([root])
        self.assertEqual(len(inventory["skills"]), 1)
        with self.assertRaises(ArmyError):
            self.inventory([root], max_files=0)
        with self.assertRaises(ArmyError):
            self.inventory([root], max_dirs=0)

    def test_file_symlink_escape(self):
        outside = self.root / "outside.md"
        outside.write_text("---\nname: outside\ndescription: escaped\n---")
        inside = self.root / "inside"
        inside.mkdir()
        try:
            (inside / "SKILL.md").symlink_to(outside)
        except OSError:
            self.skipTest("OS does not permit creating symlinks")
        inventory = self.inventory([SkillRoot(inside, "inside")])
        self.assertFalse(inventory["skills"])
        self.assertIn("escapes", inventory["diagnostics"][0]["reason"])

    def test_default_project_roots_do_not_scan_sibling(self):
        home = self.root / "home"
        project = self.root / "project"
        child = project / "nested"
        roots = default_roots("codex", project, home, child)
        paths = [r.path for r in roots]
        self.assertEqual(paths, [home / ".agents/skills", child / ".agents/skills", project / ".agents/skills"])

    def test_plugin_index_filters_other_project(self):
        current = self.root / "current"
        other = self.root / "other"
        index = self.root / "installed_plugins.json"
        index.write_text(json.dumps({"plugins": {
            "plugin@market": [
                {"scope": "user", "installPath": str(self.root / "user-install")},
                {"scope": "project", "projectPath": str(current), "installPath": str(self.root / "current-install")},
                {"scope": "project", "projectPath": str(other), "installPath": str(self.root / "other-install")},
                {"scope": "user", "installPath": str(self.root / "disabled"), "enabled": False}
            ]}}))
        roots, diagnostics = claude_plugin_roots(index, current)
        self.assertEqual(len(roots), 2)
        self.assertFalse(any("other-install" in str(r.path) for r in roots))
        self.assertTrue(diagnostics)

    def test_cli_list_refresh_resolve_and_doctor(self):
        root = self.write_skill("cli")
        for operation in ("list", "refresh", "resolve", "doctor"):
            args = ["--isolated", "skills", operation, "--host", "codex", "--root", str(root.path), "--json"]
            if operation == "resolve":
                args.extend(["--agent", "research", "--task", "literature"])
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(args)
            self.assertEqual(code, 0, stream.getvalue())
            self.assertTrue(json.loads(stream.getvalue())["ok"])

    def test_config_roots_relative_and_max_selected(self):
        root = self.write_skill("custom")
        config = self.root / "config.toml"
        config.write_text('[skills]\nmax_selected=1\nroots=[{path="custom", origin="https://example.org/skills"}]\n')
        layers = load_layers([config], set(self.registry.agents))
        self.assertEqual(layers[0][1]["skills"]["max_selected"], 1)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(["--isolated", "--config", str(config), "skills", "list", "--host", "codex", "--json"])
        data = json.loads(stream.getvalue())["data"]
        self.assertEqual(code, 0)
        self.assertEqual(data["skills"][0]["origin"], "https://example.org/skills")
        self.assertEqual(data["skills"][0]["path"], str((root.path / "SKILL.md").resolve()))

    def test_missing_pin_and_capability_match(self):
        root = self.write_skill("caps", description="No task keywords", extra="metadata:\n  army:\n    capabilities: [paper-search]\n")
        result = self.resolve(self.inventory([root]), pinned=["not-installed"], required=["paper-search"])
        self.assertEqual(result["unresolved_pins"], ["not-installed"])
        self.assertEqual(result["fallback_mode"], "skills")
        self.assertFalse(result["missing_capabilities"])

    def test_mocked_file_escape_is_not_read(self):
        root = self.write_skill("mock-escape")
        outside = self.root / "outside.md"
        real_resolve = Path.resolve
        skill_path = root.path / "SKILL.md"
        def resolve_path(path, *args, **kwargs):
            return outside if path == skill_path else real_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", resolve_path):
            inventory = self.inventory([root])
        self.assertFalse(inventory["skills"])
        self.assertIn("escapes", inventory["diagnostics"][0]["reason"])

    def test_zero_max_selected_rejected_by_cli(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(["--isolated", "skills", "resolve", "--host", "codex",
                         "--agent", "research", "--task", "literature", "--max-selected", "0", "--json"])
        self.assertEqual(code, 2)

    def test_yaml_parser_missing_is_clear_error(self):
        with patch.dict("sys.modules", {"yaml": None}):
            with self.assertRaises(ArmyError) as caught:
                self.inventory([])
            self.assertEqual(caught.exception.code, 3)

    def test_claude_frontmatter_with_real_yaml_parser(self):
        import yaml
        from agent_army.adapters.claude import render
        from agent_army.models import resolve
        for agent in self.registry.agents:
            text = render(self.registry, agent, resolve(self.registry, agent, "claude"))
            metadata = yaml.safe_load(text.split("---\n", 2)[1])
            self.assertEqual(metadata["name"], "army-" + agent)
            self.assertNotIn("skills", metadata)


if __name__ == "__main__":
    unittest.main()
