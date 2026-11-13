"""Plan files are proposals, never grants. Apply/rollback require console or authority."""
import json
from pathlib import Path

from .approvals import ConsoleAuthority
from .errors import ArmyError
from .installer import Installer
from .knowledge import Knowledge
from .migration import Migration


def add_parsers(commands):
    for name in ("install", "migration"):
        sub = commands.add_parser(name).add_subparsers(dest="operation", required=True)
        for operation in ("plan", "apply", "rollback-plan", "rollback"):
            p = sub.add_parser(operation)
            p.add_argument("--home", type=Path, help="Shared Army home; same for Claude and Codex")
            if name == "install":
                p.add_argument("--scope", choices=("user", "project"), default="user")
                p.add_argument("--claude-home", type=Path)
                p.add_argument("--codex-home", type=Path)
                p.add_argument("--python", type=Path, help="Existing Python 3.11+ interpreter for shared runtime")
                if operation == "plan":
                    p.add_argument("--host", choices=("claude", "codex", "both"), default="both")
                    p.add_argument("--action", choices=("install", "uninstall"), default="install")
                    p.add_argument("--tier", choices=("light", "medium", "heavy"))
                    p.add_argument("--remove-runtime", action="store_true")
            else:
                p.add_argument("--source", type=Path, required=True)
                p.add_argument("--source-kind", choices=("project", "global"), required=True)
                p.add_argument("--scope", choices=("project", "global"), default="project")
                if operation == "plan":
                    p.add_argument("--select", action="append", default=[], help="Exact relative legacy file; repeat to import a subset")
            if operation.endswith("plan"):
                p.add_argument("--output", type=Path, required=True, help="New JSON proposal file; never an approval grant")
                if operation == "rollback-plan":
                    p.add_argument("transaction")
            else:
                p.add_argument("--plan", type=Path, required=True)
                p.add_argument("--console", action="store_true", help="Only the person operating the terminal may use this")


def run(options, registry, layers):
    if options.command == "install":
        if options.scope == "project" and options.project is None:
            raise ArmyError("Project install requires --project")
        service = Installer(registry, home=options.home, claude_home=options.claude_home,
                            codex_home=options.codex_home, project=options.project if options.scope == "project" else None,
                            python=options.python, layers=layers)
    else:
        store = Knowledge(options.project, options.home).store(options.scope)
        service = Migration(options.source, options.source_kind, store)
    if options.operation.endswith("plan"):
        if options.operation == "rollback-plan":
            plan = service.rollback_plan(options.transaction)
        elif options.command == "install":
            plan = service.plan(action=options.action, host=options.host, tier=options.tier, remove_runtime=options.remove_runtime)
        else:
            plan = service.plan(options.select)
        # Don't overwrite the user's files, even when only saving a proposal.
        with options.output.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=True, indent=2)
        return {"plan_file": str(options.output.absolute()), "request_hash": plan["request_hash"],
                "preview": plan["preview"], "applied": False}
    try:
        if options.plan.stat().st_size > 128 * 1024 * 1024:
            raise ArmyError("Plan exceeds 128 MiB")
        plan = json.loads(options.plan.read_text(encoding="utf-8-sig"))
        if not isinstance(plan, dict) or set(plan) != {"preview", "request_hash"} or not isinstance(plan["preview"], dict):
            raise ValueError()
        if options.operation == "rollback":
            action = "install-rollback" if options.command == "install" else "migration-rollback"
            target = plan["preview"]["transaction" if options.command == "install" else "id"]
        elif options.command == "install":
            action, target = plan["preview"]["action"], str(service.home)
        else:
            action, target = "migrate", str(service.store.root)
        authority = ConsoleAuthority(action, target, plan["request_hash"], plan) if options.console else None
        return service.rollback(plan, authority) if options.operation == "rollback" else service.apply(plan, authority)
    except (KeyError, TypeError, ValueError) as exc:
        raise ArmyError("Invalid deployment plan; regenerate it", 5) from exc
