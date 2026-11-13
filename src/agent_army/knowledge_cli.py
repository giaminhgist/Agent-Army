"""Local data commands. Global mutations require a trusted adapter (not CLI flags)."""
from __future__ import annotations

import json
from pathlib import Path

from .errors import ArmyError
from .knowledge import Knowledge, initialize_project
from .paths import army_home, find_project
from .promotions import Promotions
from .store import MAX_BODY, Store


def add_parsers(commands):
    store = commands.add_parser("store").add_subparsers(dest="operation", required=True)
    init = store.add_parser("init")
    init.add_argument("--scope", choices=("project", "global"), required=True)
    for name in ("kb", "memory"):
        sub = commands.add_parser(name).add_subparsers(dest="operation", required=True)
        a = sub.add_parser("add")
        a.add_argument("--title", required=True)
        a.add_argument("--file", type=Path, required=True)
        a.add_argument("--metadata", type=Path)
        a.add_argument("--expires")
        u = sub.add_parser("update")
        u.add_argument("item")
        u.add_argument("--expected-revision", type=int, required=True)
        u.add_argument("--file", type=Path)
        u.add_argument("--title")
        u.add_argument("--metadata", type=Path)
        u.add_argument("--status", choices=("active", "superseded", "deprecated", "revoked"))
        u.add_argument("--expires")
        g = sub.add_parser("get")
        g.add_argument("item")
        g.add_argument("--scope", choices=("project", "global"), default="project")
        g.add_argument("--revision", type=int)
        l = sub.add_parser("list")
        l.add_argument("--scope", choices=("project", "global"), default="project")
        l.add_argument("--include-inactive", action="store_true")
        l.add_argument("--limit", type=int, default=1000)
        s = sub.add_parser("search")
        s.add_argument("query")
        s.add_argument("--scope", choices=("project", "global", "both"), default="both")
        s.add_argument("--limit", type=int, default=10)
        s.add_argument("--context-chars", type=int, default=16000)
        r = sub.add_parser("rebuild")
        r.add_argument("--scope", choices=("project", "global"), default="project")
    promotion = commands.add_parser("promotion").add_subparsers(dest="operation", required=True)
    prepare = promotion.add_parser("prepare")
    prepare.add_argument("item")
    prepare.add_argument("--start", type=int)
    prepare.add_argument("--end", type=int)
    prepare.add_argument("--summary-file", type=Path)
    prepare.add_argument("--title")
    prepare.add_argument("--metadata", type=Path, help="Exact target metadata to preview")
    for action in ("preview", "publish", "revoke", "reconcile"):
        action_parser = promotion.add_parser(action)
        action_parser.add_argument("promotion_id")
        if action in ("publish", "revoke"):
            action_parser.add_argument("--console", action="store_true", help="Person-operated supervised consent only")


def text_file(path: Path | None) -> str | None:
    if path is None:
        return None
    if path.suffix.lower() not in (".md", ".txt"):
        raise ArmyError("Ingest supports .md/.txt only; convert other formats explicitly first", 3)
    with path.open("rb") as stream:
        data = stream.read(MAX_BODY + 1)
    if len(data) > MAX_BODY:
        raise ArmyError("Input exceeds 4 MiB")
    return data.decode("utf-8-sig")


def metadata_file(path):
    if path is None:
        return None
    try:
        if path.stat().st_size > 64000:
            raise ArmyError("Metadata file exceeds 64k bytes")
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise ArmyError("Invalid metadata JSON") from exc
    if not isinstance(value, dict):
        raise ArmyError("Metadata JSON must be an object")
    return value


def run(options):
    project = options.project.resolve() if options.project else find_project(Path.cwd())
    if options.command == "store":
        if options.scope == "global":
            store = Store.initialize(army_home(), "global")
            return {"scope": "global", "root": str(store.root), "initialized": True}
        if project is None:
            raise ArmyError("Project initialization requires --project PATH")
        return initialize_project(project)
    knowledge = Knowledge(project)
    if options.command == "promotion":
        service = Promotions(knowledge)
        if options.operation in ("publish", "revoke") and options.console:
            from .approvals import ConsoleAuthority
            preview = service.preview(options.promotion_id)
            service.authority = ConsoleAuthority(options.operation, options.promotion_id,
                                                 preview["preview_hash"], preview)
        if options.operation == "prepare":
            return service.prepare(options.item, start=options.start, end=options.end,
                                   summary=text_file(options.summary_file), title=options.title,
                                   metadata=metadata_file(options.metadata))
        if options.operation == "preview":
            return service.preview(options.promotion_id)
        if options.operation == "publish":
            return service.apply(options.promotion_id)
        if options.operation == "revoke":
            return service.revoke(options.promotion_id)
        return service.reconcile(options.promotion_id)
    kind = "knowledge" if options.command == "kb" else "memory"
    if options.operation == "search":
        return knowledge.search(options.query, options.scope, kind, options.limit, options.context_chars)
    if options.operation in ("add", "update"):
        store = knowledge.store("project")
        if options.operation == "add":
            return store.add(kind, options.title, text_file(options.file), metadata_file(options.metadata), options.expires)
        current = store.get(options.item, include_inactive=True)
        if current["kind"] != kind:
            raise ArmyError("Item kind does not match command")
        return store.update(options.item, options.expected_revision, body=text_file(options.file),
                            title=options.title, metadata=metadata_file(options.metadata),
                            status=options.status, expires_at=options.expires)
    store = knowledge.store(options.scope)
    if options.operation == "get":
        item = store.get(options.item, options.revision)
        if item["kind"] != kind:
            raise ArmyError("Item kind does not match command")
        return item
    if options.operation == "list":
        return store.list(kind, options.include_inactive, options.limit)
    return store.rebuild()
