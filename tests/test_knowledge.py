import contextlib
import io
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agent_army.cli import main
from agent_army.config import load_layers
from agent_army.errors import ArmyError
from agent_army.knowledge import Knowledge, initialize_project, project_store
from agent_army.promotions import Promotions
from agent_army.registry import Registry
from agent_army.store import Store, chunks


class SyntheticAuthority:
    """Test-only approval provider, never imported by the production CLI."""
    def authorize(self, action, target_id, request_hash):
        return {"receipt_id": "fixture-receipt", "actor_id": "test-human",
                "action": action, "target_id": target_id, "request_hash": request_hash,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a, self.b, self.global_home = self.root / "A", self.root / "B", self.root / "global"
        self.a.mkdir()
        self.b.mkdir()
        initialize_project(self.a)
        initialize_project(self.b)
        Store.initialize(self.global_home, "global")
        self.ka = Knowledge(self.a, self.global_home)
        self.kb = Knowledge(self.b, self.global_home)
        self.pa = Promotions(self.ka, SyntheticAuthority())

    def add(self, body="Public research evidence", kind="knowledge", title="Paper", metadata=None, **kwargs):
        return self.ka.project.add(kind, title, body, metadata, **kwargs)

    def publish(self, item, **kwargs):
        preview = self.pa.prepare(item["id"], **kwargs)
        return self.pa.apply(preview["id"])

    def test_project_global_isolation_and_shared_clients(self):
        local = self.add(body="privatealpha only in project A")
        self.assertTrue(self.ka.search("privatealpha")["hits"])
        self.assertFalse(self.kb.search("privatealpha")["hits"])
        with self.assertRaises(ArmyError):
            self.kb.project.get(local["id"])
        self.publish(local)
        self.assertTrue(self.kb.search("privatealpha")["hits"])
        codex_view = Knowledge(self.a, self.global_home)
        self.assertEqual(codex_view.project.get(local["id"])["body"], "privatealpha only in project A")

    def test_read_only_search_does_not_initialize(self):
        missing = self.root / "not-created"
        result = Knowledge(global_home=missing).search("nothing")
        self.assertFalse(result["hits"])
        self.assertFalse(missing.exists())

    def test_identity_and_store_overlap(self):
        with self.assertRaises(ArmyError):
            with Store(self.ka.project.root, "project", "wrong").connect():
                pass
        with self.assertRaises(ArmyError):
            Knowledge(self.a, self.ka.project.root)
        with self.assertRaises(ArmyError):
            Store.initialize(self.global_home, "project", "wrong")

    def test_exact_document_dedup_and_doi_related_variants(self):
        one = self.add(metadata={"doi": "10.1234/EXAMPLE"})
        duplicate = self.add(metadata={"doi": "10.1234/EXAMPLE"})
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(one["id"], duplicate["id"])
        variant = self.add(body="Different interpretation", metadata={"doi": "https://doi.org/10.1234/example"})
        self.assertNotEqual(one["id"], variant["id"])
        self.assertIn(one["id"], variant["related_source_items"])
        ids = {h["item_id"] for h in self.ka.search("10.1234/example")["hits"]}
        self.assertEqual(ids, {one["id"], variant["id"]})

    def test_arxiv_exact_lookup(self):
        item = self.add(metadata={"arxiv": "2601.12345"})
        hits = self.ka.search("https://arxiv.org/abs/2601.12345")["hits"]
        self.assertEqual(hits[0]["item_id"], item["id"])

    def test_chunk_offsets_unicode_and_context_budget(self):
        body = "# Phương pháp\n\n" + ("Đánh giá trí nhớ có kiểm chứng. " * 200)
        item = self.add(body=body)
        result = self.ka.search("danh gia tri nho", context_chars=180)
        self.assertTrue(result["hits"])
        self.assertLessEqual(result["context_chars"], 180)
        for hit in result["hits"]:
            self.assertEqual(body[hit["start_offset"]:hit["end_offset"]], hit["text"])
            self.assertIn(":v1:", hit["citation"])
        self.assertEqual(self.ka.project.get(item["id"])["body"], body)

    def test_revision_cas_and_historical_content(self):
        item = self.add(body="oldword")
        newer = self.ka.project.update(item["id"], 1, body="newword")
        self.assertEqual(newer["revision"], 2)
        self.assertEqual(self.ka.project.get(item["id"], 1)["body"], "oldword")
        self.assertFalse(self.ka.search("oldword")["hits"])
        self.assertTrue(self.ka.search("newword")["hits"])
        with self.assertRaises(ArmyError) as error:
            self.ka.project.update(item["id"], 1, body="lost update")
        self.assertEqual(error.exception.code, 5)

    def test_concurrent_claude_codex_writes_conflict(self):
        item = self.add()
        barrier = threading.Barrier(2)
        def update(label):
            store = project_store(self.a)
            barrier.wait()
            try:
                store.update(item["id"], 1, body=label)
                return "saved"
            except ArmyError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(update, ["Claude revision", "Codex revision"]))
        self.assertCountEqual(outcomes, ["saved", 5])

    def test_concurrent_duplicate_adds(self):
        def add(_):
            return project_store(self.a).add("knowledge", "Same", "same source body")["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(add, range(2)))
        self.assertEqual(ids[0], ids[1])

    def test_fts_rebuild_stable_citations(self):
        self.add(body="rebuildme text")
        first = self.ka.search("rebuildme")["hits"][0]["citation"]
        self.ka.project.rebuild()
        self.assertEqual(self.ka.search("rebuildme")["hits"][0]["citation"], first)

    def test_bounded_fallback_without_fts(self):
        store = Store.initialize(self.root / "fallback", "project", "fallback-id", fts=False)
        store.add("knowledge", "Tiếng Việt", "đánh giá bằng chứng")
        result = store.search("danh gia")
        self.assertTrue(result["degraded"])
        self.assertEqual(result["ranking_method"], "bounded-text")
        self.assertTrue(result["hits"])

    def test_memory_expiry_status_applicability_and_kind_filter(self):
        self.add(body="expiredtoken", kind="memory", expires_at="2000-01-01T00:00:00Z")
        retired = self.add(body="retiredtoken", kind="memory")
        self.ka.project.update(retired["id"], 1, status="superseded")
        scoped = self.add(body="scopedtoken", kind="memory", metadata={"applies_to": [self.kb.project.project_id]})
        self.assertFalse(self.ka.search("expiredtoken")["hits"])
        self.assertFalse(self.ka.search("retiredtoken")["hits"])
        self.assertFalse(self.ka.search("scopedtoken")["hits"])
        self.add(body="knowledgeonly", kind="knowledge")
        self.assertFalse(self.ka.search("knowledgeonly", kind="memory")["hits"])

    def test_project_memory_overrides_global_key_even_different_text(self):
        with self.ka.global_store.connect(True) as c:
            self.ka.global_store._insert(c, "memory", "Preference", "globalrule",
                                         {"memory_key": "writing-language"})
        self.add(body="localrule", kind="memory", metadata={"memory_key": "writing-language"})
        self.assertFalse(self.ka.search("globalrule")["hits"])
        self.assertTrue(self.kb.search("globalrule")["hits"])
        self.assertTrue(self.ka.search("localrule")["hits"])

    def test_source_span_summary_and_metadata_selection(self):
        body = "Public evidence. SECRET PRIVATE DETAIL"
        item = self.add(body=body, metadata={"doi": "10.1/test", "source_path": "C:/private", "url": "file:///private"})
        preview = self.pa.prepare(item["id"], start=0, end=len("Public evidence."))
        target = preview["snapshot"]["target"]
        self.assertEqual(target["body"], "Public evidence.")
        self.assertNotIn("source_path", target["metadata"])
        self.assertNotIn("url", target["metadata"])
        published = self.pa.apply(preview["id"])
        global_item = self.ka.global_store.get(published["target_id"])
        self.assertNotIn("SECRET", global_item["body"])
        self.assertFalse(self.kb.search("SECRET")["hits"])
        with self.assertRaises(ArmyError):
            self.pa.prepare(item["id"], start=0, end=3, summary="both")
        summary = self.pa.prepare(item["id"], summary="Reviewed summary")
        self.assertEqual(summary["snapshot"]["target"]["body"], "Reviewed summary")

    def test_both_kinds_can_promote(self):
        for kind in ("memory", "knowledge"):
            item = self.add(kind=kind, body=f"public-{kind}")
            result = self.publish(item)
            self.assertEqual(self.ka.global_store.get(result["target_id"])["kind"], kind)

    def test_no_approval_no_publication_or_direct_global_write(self):
        item = self.add()
        service = Promotions(self.ka)
        preview = service.prepare(item["id"])
        with self.assertRaises(ArmyError) as error:
            service.apply(preview["id"])
        self.assertEqual(error.exception.code, 4)
        self.assertFalse(self.ka.global_store.list()["items"])
        with self.assertRaises(ArmyError):
            self.ka.global_store.add("knowledge", "Bypass", "not allowed")

    def test_stale_source_and_destination_rejected(self):
        item = self.add()
        preview = self.pa.prepare(item["id"])
        self.ka.project.update(item["id"], 1, body="changed")
        self.assertTrue(self.pa.preview(preview["id"])["source_stale"])
        with self.assertRaises(ArmyError):
            self.pa.apply(preview["id"])
        other_global = self.root / "different-global"
        Store.initialize(other_global, "global")
        service = Promotions(Knowledge(self.a, other_global), SyntheticAuthority())
        with self.assertRaises(ArmyError):
            service.preview(preview["id"])

    def test_expired_or_mismatched_receipt_rejected(self):
        item = self.add()
        preview = self.pa.prepare(item["id"])
        for changes in ({"request_hash": "wrong"}, {"expires_at": "2000-01-01T00:00:00Z"}, {"action": "revoke"}):
            valid = SyntheticAuthority().authorize("publish", preview["id"], preview["preview_hash"])
            authority = type("BadAuthority", (), {"authorize": lambda self, *args: valid | changes})()
            with self.assertRaises(ArmyError):
                Promotions(self.ka, authority).apply(preview["id"])

    def test_publication_retry_and_crash_recovery(self):
        item = self.add()
        preview = self.pa.prepare(item["id"])
        def crash():
            raise RuntimeError("simulated crash after global commit")
        with self.assertRaises(RuntimeError):
            self.pa.apply(preview["id"], after_global_commit=crash)
        self.assertEqual(self.pa.preview(preview["id"])["state"], "pending")
        self.assertEqual(len(self.ka.global_store.list()["items"]), 1)
        self.pa.apply(preview["id"])
        self.assertEqual(len(self.ka.global_store.list()["items"]), 1)
        self.assertEqual(self.pa.reconcile(preview["id"])["state"], "published")

    def test_reconcile_after_source_edit_does_not_republish(self):
        item = self.add()
        preview = self.pa.prepare(item["id"])
        def crash():
            raise RuntimeError("interrupted acknowledgement")
        with self.assertRaises(RuntimeError):
            self.pa.apply(preview["id"], after_global_commit=crash)
        self.ka.project.update(item["id"], 1, body="changed later")
        recovered = self.pa.reconcile(preview["id"])
        self.assertEqual(recovered["state"], "published")
        self.assertEqual(len(self.ka.global_store.list()["items"]), 1)

    def test_revoke_shared_links_and_future_retrieval(self):
        item = self.add(body="sharedrevoke")
        first, second = self.pa.prepare(item["id"]), self.pa.prepare(item["id"])
        a, b = self.pa.apply(first["id"]), self.pa.apply(second["id"])
        self.assertEqual(a["target_id"], b["target_id"])
        self.pa.revoke(first["id"])
        self.assertTrue(self.kb.search("sharedrevoke")["hits"])
        self.pa.revoke(second["id"])
        self.assertFalse(self.kb.search("sharedrevoke")["hits"])
        self.ka.global_store.rebuild()
        self.assertFalse(self.kb.search("sharedrevoke")["hits"])
        with self.assertRaises(ArmyError):
            self.pa.apply(second["id"])

    def test_revoke_does_not_remove_preexisting_global_item(self):
        item = self.add(body="retainedcontent")
        with self.ka.global_store.connect(True) as c:
            preexisting, _ = self.ka.global_store._insert(c, "knowledge", "Paper", "retainedcontent", {})
        preview = self.pa.prepare(item["id"])
        result = self.pa.apply(preview["id"])
        self.assertEqual(preexisting["id"], result["target_id"])
        self.pa.revoke(preview["id"])
        self.assertTrue(self.kb.search("retainedcontent")["hits"])

    def test_preview_tamper_and_cross_project_promotion_rejected(self):
        item = self.add()
        preview = self.pa.prepare(item["id"])
        with self.assertRaises(ArmyError):
            Promotions(self.kb).preview(preview["id"])
        with self.ka.project.connect(True) as c:
            c.execute("UPDATE promotions SET snapshot='{}' WHERE id=?", (preview["id"],))
        with self.assertRaises(ArmyError):
            self.pa.preview(preview["id"])

    def test_blob_tamper_is_detected(self):
        item = self.add()
        blob = self.ka.project.root / "blobs" / (item["body_hash"] + ".md")
        blob.write_text("tampered")
        with self.assertRaises(ArmyError):
            self.ka.project.get(item["id"])

    def test_source_blob_changed_after_preview_is_rejected(self):
        item = self.add()
        preview = self.pa.prepare(item["id"])
        blob = self.ka.project.root / "blobs" / (item["body_hash"] + ".md")
        blob.write_text("changed outside the API")
        with self.assertRaises(ArmyError):
            self.pa.apply(preview["id"])

    def test_revision_type_must_be_positive_integer(self):
        item = self.add()
        for revision in (True, 0, "1"):
            with self.assertRaises(ArmyError):
                self.ka.project.update(item["id"], revision, body="bad")

    def test_cli_init_config_and_ingest_search(self):
        new = self.root / "new-project"
        new.mkdir()
        text = self.root / "note.md"
        text.write_text("CLI evidence body")
        with patch.dict("os.environ", {"AGENT_ARMY_HOME": str(self.global_home)}):
            def cli(args):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = main(["--project", str(new), *args, "--json"])
                return code, json.loads(output.getvalue())
            code, _ = cli(["store", "init", "--scope", "project"])
            self.assertEqual(code, 0)
            load_layers([new / ".agent-army/project.toml"], set(Registry().agents))
            code, result = cli(["kb", "add", "--title", "CLI note", "--file", str(text)])
            self.assertEqual(code, 0, result)
            item_id = result["data"]["id"]
            code, result = cli(["kb", "search", "CLI evidence"])
            self.assertEqual(code, 0)
            self.assertTrue(result["data"]["hits"])
            code, result = cli(["promotion", "prepare", item_id])
            self.assertEqual(code, 0)
            promotion_id = result["data"]["id"]
            self.assertEqual(cli(["promotion", "publish", promotion_id])[0], 4)
            self.assertEqual(cli(["promotion", "publish", promotion_id, "--approved"])[0], 2)

    def test_invalid_inputs_fail_clearly(self):
        for kwargs in ({"body": ""}, {"expires_at": "tomorrow"}, {"metadata": {"applies_to": "all"}},
                       {"metadata": {"doi": 123}}):
            with self.assertRaises(ArmyError):
                self.add(**kwargs)
        with self.assertRaises(ArmyError):
            self.ka.search('"invalid*', limit=0)
        from agent_army.knowledge_cli import text_file
        with self.assertRaises(ArmyError):
            text_file(self.root / "paper.pdf")


if __name__ == "__main__":
    unittest.main()
