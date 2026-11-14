"""`army` command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from army import __version__, paths

NOT_IN_PROJECT = "Not in an Agent-Army project. Run: army init"


class CliError(Exception):
    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


def _project(required: bool = True) -> Path | None:
    p = paths.find_project()
    if p is None and required:
        raise CliError(NOT_IN_PROJECT)
    return p


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="army", description="Agent-Army: shared knowledge, memory and harness.")
    ap.add_argument("--version", action="version", version=f"army {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    kb = sub.add_parser("kb", help="knowledge base").add_subparsers(dest="kb_cmd", required=True)
    a = kb.add_parser("add", help="add a paper or note (body from --body-file or stdin)")
    a.add_argument("--type", choices=["paper", "note"], required=True)
    a.add_argument("--title", required=True)
    a.add_argument("--tags", default="")
    a.add_argument("--source", default="")
    a.add_argument("--global", dest="glob", action="store_true")
    a.add_argument("--body-file")
    s = kb.add_parser("search", help="search knowledge and memory")
    s.add_argument("query")
    s.add_argument("--scope", choices=["project", "global", "all"], default="all")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--json", action="store_true")

    mem = sub.add_parser("mem", help="memory").add_subparsers(dest="mem_cmd", required=True)
    m = mem.add_parser("add")
    m.add_argument("text")
    m.add_argument("--kind", choices=["decision", "progress", "lesson", "preference"], required=True)
    m.add_argument("--global", dest="glob", action="store_true")
    ml = mem.add_parser("list")
    ml.add_argument("--scope", choices=["project", "global"], default="project")
    ml.add_argument("--kind", choices=["decision", "progress", "lesson", "preference", "paper", "note"])
    mem.add_parser("brief")

    ini = sub.add_parser("init", help="create the project store in the current directory")
    ini.add_argument("--raw", action="append", default=[], metavar="DIR", help="read-only raw data dir (repeatable)")
    ini.add_argument("--sensitive", action="append", default=[], metavar="DIR", help="sensitive data dir (repeatable)")

    rn = sub.add_parser("run", help="run a command and record it in runs.jsonl")
    rn.add_argument("--seed", type=int)
    rn.add_argument("--out", help="main output path of the run")
    rn.add_argument("command", nargs=argparse.REMAINDER, help="-- CMD ...")
    sub.add_parser("status", help="plan, recent runs, pending promotion")

    pr = sub.add_parser("promote", help="move project items to the global store")
    pr.add_argument("ids", nargs="*")
    g = pr.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true")
    g.add_argument("--pick", action="store_true")
    g.add_argument("--reject", action="store_true", help="mark the given ids as not for global")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        return HANDLERS[args.cmd](args)
    except CliError as e:
        print(str(e), file=sys.stderr)
        return e.code


# ---- handlers -------------------------------------------------------------------------------------------------
def cmd_kb(args) -> int:
    from army import index, store

    if args.kb_cmd == "add":
        project = None if args.glob else _project()
        body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else sys.stdin.read()
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        item = store.add_item("global" if args.glob else "project", args.type, args.title, body,
                              tags=tags, source=args.source, project=project)
        print(item.id)
        return 0
    project = _project(required=args.scope == "project")
    hits = index.search(args.query, args.scope, project, args.limit)
    if args.json:
        print(json.dumps([{"scope": h.scope, "id": h.id, "title": h.title, "path": str(h.path),
                           "snippet": h.snippet} for h in hits], ensure_ascii=False, indent=2))
    elif not hits:
        print("No matches.")
    else:
        for h in hits:
            print(f"[{h.scope}] {h.id}  {h.title}\n    {h.path}\n    {h.snippet}")
    return 0


def cmd_mem(args) -> int:
    from army import brief, store

    if args.mem_cmd == "add":
        project = None if args.glob else _project()
        title = " ".join(args.text.split())[:80]
        item = store.add_item("global" if args.glob else "project", args.kind, title, args.text, project=project)
        print(item.id)
        return 0
    if args.mem_cmd == "list":
        project = _project(required=args.scope == "project")
        items = store.load_items(args.scope, project, args.kind)
        if args.kind is None:
            items = [i for i in items if i.type in store.MEMORY_TYPES]
        for i in items:
            print(f"{i.id}  [{i.type}] {i.title}")
        if not items:
            print("No memory items.")
        return 0
    text = brief.brief(_project(required=False))
    print(text or "No memory yet.")
    return 0


def cmd_promote(args) -> int:
    from army import promote

    project = _project()
    if args.list or (not args.ids and not args.pick):
        items = promote.pending(project)
        for i in items:
            print(f"{i.id}  [{i.type}] {i.title}")
        if not items:
            print("Nothing pending promotion.")
        return 0
    if args.pick:
        done = promote.pick(project)
    elif args.reject:
        try:
            promote.reject(args.ids, project)
        except KeyError as e:
            raise CliError(f"Unknown id: {e.args[0]}")
        print(f"Marked {len(args.ids)} item(s) as project-only.")
        return 0
    else:
        try:
            done = promote.promote(args.ids, project)
        except KeyError as e:
            raise CliError(f"Unknown id: {e.args[0]}")
    for i in done:
        print(f"promoted {i.id} → {i.path}")
    if not done:
        print("Nothing promoted.")
    return 0


def cmd_init(args) -> int:
    from army import project

    root = Path.cwd()
    st = project.init_project(root, args.raw, args.sensitive)
    cfg = project.load_project(root)
    print(f"Agent-Army project ready: {st}")
    print(f"  raw (read-only): {', '.join(cfg['raw_dirs']) or '-'}")
    print(f"  sensitive:       {', '.join(cfg['sensitive_dirs']) or '-'}")
    return 0


def cmd_run(args) -> int:
    from army import runlog

    project = _project()
    cmd = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not cmd:
        raise CliError("usage: army run [--seed N] [--out PATH] -- CMD ...")
    rec = runlog.run(cmd, project, seed=args.seed, out=args.out)
    print(f"[army] run_id={rec['run_id']} exit={rec['exit_code']} log={rec['log']}", file=sys.stderr)
    return rec["exit_code"]


def cmd_status(args) -> int:
    from army import status

    print(status.status_text(_project()))
    return 0


HANDLERS = {"init": cmd_init, "run": cmd_run, "status": cmd_status, "kb": cmd_kb, "mem": cmd_mem, "promote": cmd_promote}
