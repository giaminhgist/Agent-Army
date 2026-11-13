import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agent_army.cli import main
from agent_army.errors import ArmyError
from agent_army.installer import Installer
from agent_army.knowledge import initialize_project, project_store
from agent_army.migration import Migration
from agent_army.registry import Registry
from agent_army.store import Store
from agent_army import transactions as tx


class Authority:
    def authorize(self, action, target_id, request_hash):
        return {"action": action, "target_id": target_id, "request_hash": request_hash,
                "actor_id": "test-only", "receipt_id": "synthetic",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "shared"
        self.claude, self.codex = self.root / "claude", self.root / "codex"
        self.registry, self.auth = Registry(), Authority()
        self.installer = Installer(self.registry, home=self.home, claude_home=self.claude, codex_home=self.codex)

    def install(self, **kwargs):
        return self.installer.apply(self.installer.plan(**kwargs), self.auth)

    def test_plan_read_only_and_no_default_consent(self):
        plan = self.installer.plan()
        self.assertFalse(self.home.exists())
        self.assertFalse(self.claude.exists())
        with self.assertRaises(ArmyError):
            self.installer.apply(plan)
        self.assertFalse(self.home.exists())

    def test_fresh_both_shared_runtime_no_skills(self):
        self.install()
        self.assertEqual(len(list((self.claude / "agents").glob("army-*.md"))), 11)
        self.assertEqual(len(list((self.codex / "agents").glob("army-*.toml"))), 11)
        for folder in (self.claude, self.codex):
            self.assertFalse((folder / "skills").exists())
        result = subprocess.run([sys.executable, str(self.home / "bin/army.py"), "version", "--json"], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["data"]["version"], "0.5.0")

    def test_reinstall_noop(self):
        self.install()
        self.assertEqual(self.install()["state"], "unchanged")

    def test_user_files_and_configs_unchanged(self):
        for folder, name in ((self.claude, "settings.json"), (self.codex, "config.toml")):
            folder.mkdir()
            (folder / name).write_bytes(b"personal config\r\n")
            (folder / "agents").mkdir()
            (folder / "agents/custom.md").write_bytes(b"personal agent")
        self.install()
        self.install(action="uninstall", remove_runtime=True)
        self.assertEqual((self.claude / "settings.json").read_bytes(), b"personal config\r\n")
        self.assertEqual((self.codex / "config.toml").read_bytes(), b"personal config\r\n")
        self.assertTrue((self.claude / "agents/custom.md").exists())

    def test_unowned_collision_and_edited_uninstall_block(self):
        (self.claude / "agents").mkdir(parents=True)
        target = self.claude / "agents/army-research.md"
        target.write_text("mine")
        plan = self.installer.plan()
        self.assertTrue(plan["preview"]["conflicts"])
        with self.assertRaises(ArmyError):
            self.installer.apply(plan, self.auth)
        target.unlink()
        self.install()
        target.write_text("edited")
        with self.assertRaises(ArmyError):
            self.install(action="uninstall")
        self.assertEqual(target.read_text(), "edited")

    def test_update_backup_and_rollback(self):
        self.install()
        target = self.claude / "agents/army-research.md"
        original = target.read_bytes()
        self.registry.prompts["research"] += "\nUpdated research instructions.\n"
        result = self.install()
        self.assertNotEqual(target.read_bytes(), original)
        self.installer.rollback(self.installer.rollback_plan(result["transaction"]), self.auth)
        self.assertEqual(target.read_bytes(), original)

    def test_partial_failure_restores_original_bytes(self):
        plan = self.installer.plan()
        def failure(index):
            if index == 3:
                raise OSError("synthetic disk failure")
        with self.assertRaises(OSError):
            self.installer.apply(plan, self.auth, fault=failure)
        self.assertFalse(list(self.claude.rglob("army-*.md")))
        self.assertFalse(self.installer.manifest.exists())
        self.install()

    def test_crash_journal_recovery(self):
        class Crash(BaseException):
            pass
        def crash(index):
            if index == 1:
                raise Crash()
        with self.assertRaises(Crash):
            self.installer.apply(self.installer.plan(), self.auth, fault=crash)
        transaction = next((self.home / "installer/transactions").glob("*.json")).stem
        plan = self.installer.rollback_plan(transaction)
        self.installer.rollback(plan, self.auth)
        self.assertFalse(list(self.claude.rglob("army-*.md")))
        self.install()

    def test_rollback_preserves_post_install_edits(self):
        result = self.install()
        target = self.claude / "agents/army-research.md"
        target.write_text("user changed")
        plan = self.installer.rollback_plan(result["transaction"])
        self.assertTrue(plan["preview"]["conflicts"])
        with self.assertRaises(ArmyError):
            self.installer.rollback(plan, self.auth)
        self.assertEqual(target.read_text(), "user changed")

    def test_stale_preview_rejected(self):
        plan = self.installer.plan()
        self.registry.prompts["research"] += "changed"
        with self.assertRaises(ArmyError):
            self.installer.apply(plan, self.auth)

    def test_single_host_uninstall_keeps_other_and_memory(self):
        self.install()
        Store.initialize(self.home, "global")
        before = (self.home / "store.sqlite").read_bytes()
        with self.assertRaises(ArmyError):
            self.installer.plan(action="uninstall", host="claude", remove_runtime=True)
        self.install(action="uninstall", host="claude")
        self.assertFalse(list((self.claude / "agents").glob("army-*")))
        self.assertEqual(len(list((self.codex / "agents").glob("army-*"))), 11)
        self.assertEqual((self.home / "store.sqlite").read_bytes(), before)

    def test_project_scope_does_not_initialize_knowledge(self):
        project = self.root / "project"
        project.mkdir()
        service = Installer(self.registry, home=self.home, project=project)
        service.apply(service.plan(), self.auth)
        self.assertEqual(len(list((project / ".codex/agents").glob("*.toml"))), 11)
        self.assertFalse((project / ".agent-army").exists())
        self.assertFalse(self.claude.exists())

    def test_cli_saved_plan_and_no_apply(self):
        output = self.root / "plan.json"
        common = ["--isolated", "install"]
        roots = ["--home", str(self.home), "--claude-home", str(self.claude), "--codex-home", str(self.codex)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(common + ["plan", *roots, "--output", str(output), "--json"]), 0)
            self.assertEqual(main(common + ["apply", *roots, "--plan", str(output), "--json"]), 4)
        self.assertFalse(self.home.exists())

    def test_installer_cooperative_lock(self):
        with tx.lock(self.installer.state):
            with self.assertRaises(ArmyError):
                with tx.lock(self.installer.state):
                    self.fail("Second lock acquired")

    def test_corrupt_manifest_path_rejected(self):
        self.install()
        manifest = json.loads(self.installer.manifest.read_text())
        manifest["files"][str(self.root / "personal.txt")] = {"group": "runtime", "hash": "fake"}
        self.installer.manifest.write_text(json.dumps(manifest))
        with self.assertRaises(ArmyError):
            self.installer.plan(action="uninstall", remove_runtime=True)

    def test_source_and_runtime_read_only_plan(self):
        original = (self.registry.root / "prompts/protocol.md").read_bytes()
        self.installer.plan(host="codex")
        self.assertEqual((self.registry.root / "prompts/protocol.md").read_bytes(), original)
        self.assertFalse(self.home.exists())


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source, self.project = self.root / "legacy", self.root / "new"
        self.source.mkdir()
        self.project.mkdir()
        initialize_project(self.project)
        self.store, self.auth = project_store(self.project), Authority()
        self.write(".research-agent/kb/papers/p.md", b'---\ntitle: "Paper"\ndoi: "10.1/example"\nslug: p\n---\nEvidence [@p] [note](../notes/n.md)\r\n')
        self.write(".research-agent/kb/notes/n.md", b"Notes")
        self.write(".research-agent/kb/library.bib", b"@article{p, title={Paper}}")
        self.write(".research-agent/memory/decisions.md", "Quyết định nghiên cứu".encode())
        self.write(".research-agent/memory/state.json", b'{"auto": true}')
        self.write(".research-agent/tasks/tasks.json", b'{"T001":{"state":"dispatched"}}')
        self.write(".research-agent/approvals/granted.jsonl", b'{"approved":true}')
        self.service = Migration(self.source, "project", self.store)

    def write(self, relative, data):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_preview_counts_excludes_grants_and_archives_jobs(self):
        plan = self.service.plan()["preview"]
        self.assertEqual(plan["counts"], {"files": 6, "import": 3})
        self.assertFalse(plan["unresolved_citation_keys"])
        self.assertFalse(plan["unresolved_relative_links"])
        entries = {e["source"]: e for e in plan["entries"]}
        self.assertEqual(entries[".research-agent/tasks/tasks.json"]["mode"], "archive_only")
        self.assertEqual(entries[".research-agent/memory/state.json"]["mode"], "archive_only")
        self.assertNotIn(".research-agent/approvals/granted.jsonl", entries)
        self.assertEqual(self.store.list()["items"], [])

    def test_import_copy_mapping_hash_links_idempotency(self):
        originals = {str(p): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        plan = self.service.plan()
        result = self.service.apply(plan, self.auth)
        self.assertEqual(len(result["mapping"]), 6)
        for entry in result["mapping"]:
            self.assertEqual((self.store.root / entry["snapshot"]).read_bytes(), (self.source / entry["source"]).read_bytes())
        self.assertEqual(self.service.apply(plan, self.auth)["mapping"], result["mapping"])
        self.assertEqual(len(self.store.list()["items"]), 3)
        self.assertEqual(originals, {str(p): p.read_bytes() for p in self.source.rglob("*") if p.is_file()})
        self.assertTrue(self.store.search("10.1/example")["hits"])

    def test_no_authority_and_changed_source(self):
        plan = self.service.plan()
        with self.assertRaises(ArmyError):
            self.service.apply(plan)
        self.write(".research-agent/kb/notes/n.md", b"changed")
        with self.assertRaises(ArmyError):
            self.service.apply(plan, self.auth)
        self.assertEqual(self.store.list()["items"], [])

    def test_import_failure_atomic_records(self):
        plan = self.service.plan()
        def failure(index):
            if index == 2:
                raise OSError("synthetic failure")
        with self.assertRaises(OSError):
            self.service.apply(plan, self.auth, fault=failure)
        self.assertEqual(self.store.list()["items"], [])
        result = self.service.apply(plan, self.auth)
        self.assertEqual(result["state"], "imported")

    def test_rollback_keeps_source_snapshot_and_existing_data(self):
        existing = self.store.add("memory", "Existing", "keep me")
        result = self.service.apply(self.service.plan(), self.auth)
        self.service.rollback(self.service.rollback_plan(result["id"]), self.auth)
        self.assertEqual([x["id"] for x in self.store.list()["items"]], [existing["id"]])
        self.assertTrue((self.store.root / result["mapping"][0]["snapshot"]).is_file())
        self.assertTrue((self.source / ".research-agent/kb/papers/p.md").exists())

    def test_rollback_edited_item_conflict(self):
        result = self.service.apply(self.service.plan(), self.auth)
        item = next(e for e in result["mapping"] if e["item_id"])
        self.store.update(item["item_id"], 1, body="User updated")
        plan = self.service.rollback_plan(result["id"])
        self.assertTrue(plan["preview"]["conflicts"])
        with self.assertRaises(ArmyError):
            self.service.rollback(plan, self.auth)

    def test_select_and_bad_selection(self):
        selected = [".research-agent/kb/papers/p.md"]
        plan = self.service.plan(selected)
        self.assertEqual(plan["preview"]["counts"]["files"], 1)
        self.assertTrue(plan["preview"]["unresolved_relative_links"])
        with self.assertRaises(ArmyError):
            self.service.plan([".research-agent/approvals/granted.jsonl"])
        with self.assertRaises(ArmyError):
            self.service.plan(["../escape.md"])

    def test_global_legacy_import_is_separately_approved(self):
        source = self.root / "old-global"
        (source / "knowledge/notes").mkdir(parents=True)
        (source / "knowledge/notes/g.md").write_text("Shared evidence")
        store = Store.initialize(self.root / "new-global", "global")
        service = Migration(source, "global", store)
        with self.assertRaises(ArmyError):
            service.apply(service.plan())
        result = service.apply(service.plan(), self.auth)
        self.assertEqual(len(store.list()["items"]), 1)
        service.rollback(service.rollback_plan(result["id"]), self.auth)
        self.assertEqual(store.list()["items"], [])

    def test_source_changed_during_import_rolls_back(self):
        plan = self.service.plan()
        def change(index):
            if index == 0:
                self.write(".research-agent/kb/notes/n.md", b"racing writer")
        with self.assertRaises(ArmyError):
            self.service.apply(plan, self.auth, fault=change)
        self.assertEqual(self.store.list()["items"], [])

    def test_crlf_body_roundtrip_exact(self):
        result = self.service.apply(self.service.plan(), self.auth)
        entry = next(e for e in result["mapping"] if e["source"].endswith("papers/p.md"))
        self.assertEqual(self.store.get(entry["item_id"])["body"], (self.source / entry["source"]).read_bytes().decode())

    def test_shared_migration_reference_last_rollback(self):
        first = self.service.apply(self.service.plan(), self.auth)
        second = self.service.apply(self.service.plan([".research-agent/kb/papers/p.md"]), self.auth)
        self.service.rollback(self.service.rollback_plan(first["id"]), self.auth)
        self.assertEqual(len(self.store.list()["items"]), 1)
        self.service.rollback(self.service.rollback_plan(second["id"]), self.auth)
        self.assertEqual(self.store.list()["items"], [])

    def test_preexisting_matching_item_preserved(self):
        plan = self.service.plan([".research-agent/kb/papers/p.md"])
        entry = plan["preview"]["entries"][0]["record"]
        existing = self.store.add(**entry)
        result = self.service.apply(self.service.plan([".research-agent/kb/papers/p.md"]), self.auth)
        self.service.rollback(self.service.rollback_plan(result["id"]), self.auth)
        self.assertEqual(self.store.get(existing["id"])["title"], "Paper")

    def test_snapshot_collision_not_overwritten(self):
        plan = self.service.plan()
        entry = plan["preview"]["entries"][0]
        path = self.store.root / "migrations" / plan["request_hash"] / "snapshot" / entry["source"]
        path.parent.mkdir(parents=True)
        path.write_bytes(b"manual data")
        with self.assertRaises(ArmyError):
            self.service.apply(plan, self.auth)
        self.assertEqual(path.read_bytes(), b"manual data")

    def test_binary_is_archived_without_ingest(self):
        self.write(".research-agent/kb/papers/source.pdf", b"%PDF-1.7\x00\xff")
        plan = self.service.plan([".research-agent/kb/papers/source.pdf"])
        self.assertEqual(plan["preview"]["counts"], {"files": 1, "import": 0})
        result = self.service.apply(plan, self.auth)
        self.assertEqual((self.store.root / result["mapping"][0]["snapshot"]).read_bytes(), b"%PDF-1.7\x00\xff")


if __name__ == "__main__":
    unittest.main()
