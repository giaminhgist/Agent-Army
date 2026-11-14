import contextlib
import io

from tests.helpers import TempHome

from army import brief, cli, index, promote, store


def run_cli(args, stdin=""):
    out, err = io.StringIO(), io.StringIO()
    import sys
    old = sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(args)
    finally:
        sys.stdin = old
    return code, out.getvalue(), err.getvalue()


class PromoteTests(TempHome):
    def setUp(self):
        super().setUp()
        self.make_project()

    def test_promote_copies_with_origin_and_is_idempotent(self):
        it = store.add_item("project", "paper", "P1", "content", project=self.proj)
        out = promote.promote([it.id], self.proj)
        self.assertEqual(len(out), 1)
        g = store.get_item(it.id, "global")
        self.assertEqual(g.meta["scope"], "global")
        self.assertEqual(g.meta["origin_project"], str(self.proj))
        self.assertNotIn("promote", g.meta)
        self.assertEqual(store.get_item(it.id, "project", self.proj).meta["promote"], "yes")
        self.assertEqual(promote.promote([it.id], self.proj), [])
        self.assertEqual(len(store.load_items("global")), 1)
        self.assertEqual(promote.pending(self.proj), [])

    def test_promote_unknown_id_raises(self):
        with self.assertRaises(KeyError):
            promote.promote(["nope"], self.proj)

    def test_reject(self):
        it = store.add_item("project", "note", "N", "c", project=self.proj)
        promote.reject([it.id], self.proj)
        self.assertEqual(promote.pending(self.proj), [])

    def test_pick_parses_selection(self):
        a = store.add_item("project", "note", "A", "c", project=self.proj)
        store.add_item("project", "note", "B", "c", project=self.proj)
        sink = []
        got = promote.pick(self.proj, input_fn=lambda _p: "none", print_fn=sink.append)
        self.assertEqual(got, [])
        answers = iter(["x", "x"])
        got = promote.pick(self.proj, input_fn=lambda _p: next(answers), print_fn=sink.append)
        self.assertEqual(got, [])
        pend = promote.pending(self.proj)
        idx = [i.id for i in pend].index(a.id) + 1
        got = promote.pick(self.proj, input_fn=lambda _p: str(idx), print_fn=sink.append)
        self.assertEqual([i.id for i in got], [a.id])
        got = promote.pick(self.proj, input_fn=lambda _p: "all", print_fn=sink.append)
        self.assertEqual(len(got), 1)
        self.assertEqual(promote.pending(self.proj), [])

    def test_brief_empty_is_empty_string(self):
        self.assertEqual(brief.brief(self.proj), "")
        self.assertEqual(brief.brief(None), "")

    def test_brief_sections_and_pending_line(self):
        (self.proj / ".agent-army" / "plan.md").write_text("- [ ] Task A\n- [x] Task B\n")
        store.add_item("project", "decision", "Use subject-level CV", "", project=self.proj)
        store.add_item("project", "progress", "Baseline done", "", project=self.proj)
        store.add_item("project", "note", "Some note", "", project=self.proj)
        store.add_item("global", "preference", "Answer in Vietnamese", "")
        b = brief.brief(self.proj)
        self.assertIn("# Agent-Army memory", b)
        self.assertIn("## Open tasks", b)
        self.assertIn("Task A", b)
        self.assertNotIn("Task B", b)
        self.assertIn("## Recent decisions", b)
        self.assertIn("Use subject-level CV", b)
        self.assertIn("## Progress", b)
        self.assertIn("## Global lessons & preferences", b)
        self.assertIn("Answer in Vietnamese", b)
        self.assertIn("1 item(s) pending promotion → army promote --pick", b)
        self.assertLessEqual(len(brief.brief(self.proj, max_chars=50)), 50)

    def test_cli_kb_add_and_search(self):
        code, out, _ = run_cli(["kb", "add", "--type", "paper", "--title", "Scanpath SSL", "--tags", "eye,ssl"],
                               stdin="self-supervised scanpath representations")
        self.assertEqual(code, 0)
        item_id = out.strip()
        self.assertTrue(item_id.startswith("paper-scanpath-ssl-"))
        code, out, _ = run_cli(["kb", "search", "scanpath"])
        self.assertEqual(code, 0)
        self.assertIn(item_id, out)
        code, out, _ = run_cli(["mem", "add", "Always seed 3 runs", "--kind", "lesson", "--global"])
        self.assertEqual(code, 0)
        code, out, _ = run_cli(["mem", "list", "--scope", "global"])
        self.assertIn("Always seed 3 runs", out)
        code, out, _ = run_cli(["promote", "--list"])
        self.assertIn(item_id, out)
        code, out, _ = run_cli(["promote", item_id])
        self.assertEqual(code, 0)
        self.assertEqual(len(index.search("scanpath", "global")), 1)

    def test_cli_outside_project_exits_2(self):
        import os
        os.chdir(self.home)
        code, _, err = run_cli(["kb", "search", "x", "--scope", "project"])
        self.assertEqual(code, 2)
        self.assertIn("Not in an Agent-Army project. Run: army init", err)
        code, _, _ = run_cli(["mem", "add", "global ok", "--kind", "lesson", "--global"])
        self.assertEqual(code, 0)
