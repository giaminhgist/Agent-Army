import os
import time

from tests.helpers import TempHome

from army import index, store


class StoreTests(TempHome):
    def setUp(self):
        super().setUp()
        self.make_project()

    def test_add_and_load(self):
        p = store.add_item("project", "paper", "Gaze biomarkers", "body", tags=["eye"], project=self.proj)
        d = store.add_item("project", "decision", "Use 5-fold CV", "why", project=self.proj)
        self.assertEqual(p.meta["promote"], "pending")
        self.assertEqual(d.meta["promote"], "no")
        self.assertEqual(p.path.parent.name, "knowledge")
        self.assertEqual(d.path.parent.name, "memory")
        self.assertTrue(p.path.is_file())
        self.assertEqual(p.meta["origin_project"], str(self.proj))
        loaded = store.load_items("project", self.proj)
        self.assertEqual({i.id for i in loaded}, {p.id, d.id})
        self.assertEqual(store.get_item(p.id, "project", self.proj).title, "Gaze biomarkers")
        with self.assertRaises(ValueError):
            store.add_item("project", "bogus", "t", "b", project=self.proj)

    def test_global_item_has_no_promote(self):
        g = store.add_item("global", "lesson", "Seeds matter", "b")
        self.assertNotIn("promote", g.meta)
        self.assertEqual(g.scope, "global")

    def test_update_meta(self):
        p = store.add_item("project", "note", "n1", "b", project=self.proj)
        store.update_meta(p, promote="yes")
        self.assertEqual(store.get_item(p.id, "project", self.proj).meta["promote"], "yes")

    def test_search_project_before_global(self):
        store.add_item("global", "note", "Global transformer note", "transformer attention", )
        store.add_item("project", "note", "Project transformer note", "transformer attention", project=self.proj)
        hits = index.search("transformer", "all", self.proj)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].scope, "project")
        self.assertEqual(hits[1].scope, "global")

    def test_search_scope_isolation(self):
        store.add_item("global", "note", "Only global", "zebrafish")
        self.assertEqual(index.search("zebrafish", "project", self.proj), [])
        self.assertEqual(len(index.search("zebrafish", "global", None)), 1)

    def test_index_updates_on_edit_and_delete(self):
        it = store.add_item("project", "note", "n", "alpha", project=self.proj)
        self.assertEqual(len(index.search("alpha", "project", self.proj)), 1)
        time.sleep(0.01)
        it.path.write_text(it.path.read_text().replace("alpha", "beta"))
        os.utime(it.path, (time.time() + 5, time.time() + 5))
        self.assertEqual(index.search("alpha", "project", self.proj), [])
        self.assertEqual(len(index.search("beta", "project", self.proj)), 1)
        it.path.unlink()
        self.assertEqual(index.search("beta", "project", self.proj), [])

    def test_search_odd_queries_and_diacritics(self):
        store.add_item("project", "note", "Ghi chú", "kiến thức nền", project=self.proj)
        for q in ['"', "a-b:c*", "(", "", "AND OR NOT"]:
            self.assertIsInstance(index.search(q, "all", self.proj), list)
        hits = index.search("kien thuc", "project", self.proj)
        self.assertEqual(len(hits), 1)

    def test_corrupt_index_rebuilds(self):
        store.add_item("project", "note", "n", "gamma", project=self.proj)
        index.search("gamma", "project", self.proj)
        (self.proj / ".agent-army" / "index.sqlite").write_bytes(b"garbage" * 100)
        self.assertEqual(len(index.search("gamma", "project", self.proj)), 1)
