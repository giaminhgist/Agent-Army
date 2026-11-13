import contextlib
import io
import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_army.adapters import claude, codex
from agent_army.build import build
from agent_army.cli import main
from agent_army.config import load_layers, merge
from agent_army.errors import ArmyError
from agent_army.models import resolve
from agent_army.paths import contained, find_project
from agent_army.registry import Registry, default_resources
from agent_army.routing import route, validate_graph


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = Registry()

    def resources(self):
        root = self.root / 'resources'
        shutil.copytree(default_resources(), root)
        return root

    def test_bundled_roles_and_recommendations(self):
        expected = {'orchestrator', 'research', 'methodology', 'data-steward', 'coding', 'experiment',
                    'statistical-analyst', 'visualization', 'writing', 'reviewer', 'knowledge-curator'}
        self.assertEqual(set(self.registry.agents), expected)
        for agent in expected:
            self.assertEqual(len(self.registry.suggestions(agent)), 6)
            for host in ('claude', 'codex'):
                for tier in ('light', 'medium', 'heavy'):
                    profile = resolve(self.registry, agent, host, tier)
                    self.assertEqual(profile['availability'], 'unknown')
                    self.assertFalse(profile['execution_authorized'])

    def test_custom_agent_and_no_recommendations(self):
        root = self.resources()
        file = root / 'registry/agents.toml'
        with file.open('a', encoding='utf-8') as stream:
            stream.write('\n[agents.custom-specialist]\ndescription="Custom"\nrole="Custom specialist"\n'
                         'prompt_path="prompts/research.md"\ndefault_tier="light"\n'
                         'capabilities=["custom-task"]\nkeywords=["customtask"]\noutput_contract="custom-report"\n')
        (root / 'registry/recommendations.toml').unlink()
        registry = Registry(root)
        self.assertEqual(len(registry.agents), 12)
        self.assertEqual(registry.suggestions('research'), [])
        self.assertEqual(route(registry, 'customtask')['agent'], 'custom-specialist')
        self.assertEqual(build(registry, self.root / 'generated')['generated_count'], 24)

    def test_duplicate_agent_rejected(self):
        root = self.resources()
        with (root / 'registry/agents.toml').open('a', encoding='utf-8') as stream:
            stream.write('\n[agents.research]\nrole="Duplicate"\n')
        with self.assertRaises(ArmyError):
            Registry(root)

    def test_missing_and_escaping_prompt_rejected(self):
        root = self.resources()
        prompt = root / 'prompts/research.md'
        prompt.unlink()
        with self.assertRaises(ArmyError):
            Registry(root)
        file = root / 'registry/agents.toml'
        file.write_text(file.read_text().replace('prompts/research.md', 'prompts/../../outside.md'))
        with self.assertRaises(ArmyError):
            Registry(root)

    def test_unknown_fields_fail_instead_of_silent_loss(self):
        root = self.resources()
        file = root / 'registry/agents.toml'
        file.write_text(file.read_text().replace('[agents.research]', '[agents.research]\nsandbox_mode="read-only"'))
        with self.assertRaisesRegex(ArmyError, 'unknown keys'):
            Registry(root)

    def test_model_precedence(self):
        layers = [('global', {'models': {'codex': {'light': {'model': 'global-model'}}},
                              'agents': {'research': {'models': {'codex': {'light': {'model': 'global-agent'}}}}}}),
                  ('project', {'models': {'codex': {'light': {'model': 'project-model'}}},
                               'agents': {'research': {'models': {'codex': {'light': {'model': 'project-agent', 'effort': 'high'}}}}}})]
        profile = resolve(self.registry, 'research', 'codex', layers=layers)
        self.assertEqual(profile['model'], 'project-agent')
        self.assertEqual(profile['origins']['model'], 'project:agent')
        profile = resolve(self.registry, 'research', 'codex', layers=layers, task_profile={'model': 'task-model'})
        self.assertEqual(profile['model'], 'task-model')
        self.assertNotIn('effort', profile)
        self.assertEqual(profile['origins']['model'], 'task-preview')

    def test_agent_default_tier_override(self):
        layers = [('project', {'agents': {'research': {'default_tier': 'heavy'}}})]
        self.assertEqual(resolve(self.registry, 'research', 'claude', layers=layers)['model'], 'fable')
        self.assertEqual(resolve(self.registry, 'research', 'claude', 'light', layers)['model'], 'sonnet')

    def test_bad_host_tier_and_effort(self):
        for kwargs in ({'host': 'unknown'}, {'host': 'codex', 'tier': 'super_heavy'},
                       {'host': 'codex', 'task_profile': {'effort': 'imaginary'}}):
            with self.assertRaises(ArmyError):
                resolve(self.registry, 'research', **kwargs)

    def test_config_roundtrip_and_unknown_key(self):
        path = self.root / 'config.toml'
        path.write_text('schema_version=1\n[agents.research]\ndefault_tier="medium"\n'
                        '[agents.research.models.codex.medium]\nmodel="custom-model"\neffort="low"\n')
        layers = load_layers([path], set(self.registry.agents))
        self.assertEqual(resolve(self.registry, 'research', 'codex', layers=layers)['model'], 'custom-model')
        path.write_text('[models.codex.light]\nmodle="typo"\n')
        with self.assertRaisesRegex(ArmyError, 'unknown keys'):
            load_layers([path], set(self.registry.agents))

    def test_deep_merge_replaces_lists_without_mutation(self):
        original = {'a': {'x': 1, 'list': [1, 2]}}
        self.assertEqual(merge(original, {'a': {'list': [3]}}), {'a': {'x': 1, 'list': [3]}})
        self.assertEqual(original['a']['list'], [1, 2])

    def test_native_documents_parse_and_no_required_skills(self):
        for agent in self.registry.agents:
            for host in ('claude', 'codex'):
                profile = resolve(self.registry, agent, host)
                if host == 'codex':
                    document = tomllib.loads(codex.render(self.registry, agent, profile))
                    self.assertIn('developer_instructions', document)
                    self.assertNotIn('sandbox_mode', document)
                else:
                    text = claude.render(self.registry, agent, profile)
                    frontmatter = text.split('---\n', 2)[1]
                    # Validate the deliberately limited YAML subset: string keys + JSON quoted scalars.
                    document = {key: json.loads(value.strip()) for key, value in
                                (line.split(':', 1) for line in frontmatter.strip().splitlines())}
                    self.assertEqual(set(document), {'name', 'description', 'model'})
                self.assertEqual(document['name'], 'army-' + agent)
                self.assertEqual(document['model'], profile['model'])
                self.assertNotIn('skills', document)

    def test_render_escaping(self):
        root = self.resources()
        (root / 'prompts/research.md').write_text('Quotes """ and backslashes \\ and Unicode: nghiên cứu\n', encoding='utf-8')
        registry = Registry(root)
        parsed = tomllib.loads(codex.render(registry, 'research', resolve(registry, 'research', 'codex')))
        self.assertIn('nghiên cứu', parsed['developer_instructions'])
        self.assertIn('"""', parsed['developer_instructions'])

    def test_build_deterministic_and_preserves_manual_edits(self):
        output = self.root / 'build'
        first = build(self.registry, output)
        manifest = (output / 'manifest.json').read_bytes()
        self.assertEqual(first['generated_count'], 22)
        before = {p: (output / p).read_bytes() for p in first['files']}
        build(self.registry, output)
        self.assertEqual((output / 'manifest.json').read_bytes(), manifest)
        self.assertEqual(before, {p: (output / p).read_bytes() for p in first['files']})
        edited = output / first['files'][-1]
        edited.write_text('USER EDIT')
        with self.assertRaises(ArmyError) as caught:
            build(self.registry, output)
        self.assertEqual(caught.exception.code, 5)
        self.assertEqual(edited.read_text(), 'USER EDIT')

    def test_unowned_and_native_output_rejected(self):
        output = self.root / 'build'
        target = output / 'claude/agents/army-research.md'
        target.parent.mkdir(parents=True)
        target.write_text('existing file')
        with self.assertRaises(ArmyError):
            build(self.registry, output)
        self.assertFalse((output / 'manifest.json').exists())
        for folder in ('.claude', '.codex', '.agents', '.agent-army'):
            with self.assertRaises(ArmyError):
                build(self.registry, self.root / folder / 'agents')

    def test_build_refresh_with_new_source(self):
        root = self.resources()
        output = self.root / 'build'
        build(Registry(root), output)
        with (root / 'prompts/research.md').open('a', encoding='utf-8') as stream:
            stream.write('\nAdditional requirement.\n')
        build(Registry(root), output)
        self.assertIn('Additional requirement.', (output / 'claude/agents/army-research.md').read_text())

    def test_corrupt_manifest_fails_cleanly(self):
        output = self.root / 'build'
        output.mkdir()
        (output / 'manifest.json').write_text('[]')
        with self.assertRaises(ArmyError) as caught:
            build(self.registry, output)
        self.assertEqual(caught.exception.code, 5)

    def test_routing_english_vietnamese_review_and_explicit(self):
        for task, expected in [('debug training bug', 'coding'), ('tổng quan tài liệu', 'research'),
                               ('phản biện code', 'reviewer'), ('review literature', 'reviewer'),
                               ('something unclear', 'orchestrator')]:
            self.assertEqual(route(self.registry, task)['agent'], expected)
        self.assertEqual(route(self.registry, 'review', 'writing')['agent'], 'writing')
        self.assertEqual(route(self.registry, 'do this', task_type='statistical-analysis')['agent'], 'statistical-analyst')

    def test_graph_cycles_and_missing_dependencies(self):
        validate_graph({'a': [], 'b': ['a']})
        for graph in ({'a': ['b']}, {'a': ['b'], 'b': ['a']}):
            with self.assertRaises(ArmyError):
                validate_graph(graph)

    def test_project_and_path_boundaries(self):
        state = self.root / '.agent-army'
        state.mkdir()
        (state / 'project.toml').write_text('schema_version=1')
        child = self.root / 'nested'
        child.mkdir()
        self.assertEqual(find_project(child), self.root)
        with self.assertRaises(ArmyError):
            contained(self.root, '../other/file')

    def test_cli_json_success_and_failures(self):
        for args, expected in [(['--isolated', 'agents', 'validate'], 0),
                               (['--isolated', 'models', 'resolve', '--agent', 'missing', '--host', 'codex'], 2),
                               (['--isolated', 'unknown'], 2), (['version'], 0),
                               (['--isolated', 'doctor'], 0)]:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([*args, '--json'])
            result = json.loads(output.getvalue())
            self.assertEqual(code, expected)
            self.assertEqual(result['ok'], expected == 0)

    def test_isolated_cli_does_not_read_user_config(self):
        fake_home = self.root / 'home'
        fake_home.mkdir()
        (fake_home / 'config.toml').write_text('invalid toml = !!!')
        with patch.dict('os.environ', {'AGENT_ARMY_HOME': str(fake_home)}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--isolated', 'agents', 'validate', '--json']), 0)
                self.assertEqual(main(['agents', 'validate', '--json']), 2)


if __name__ == '__main__':
    unittest.main()
