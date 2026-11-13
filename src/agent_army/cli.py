from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .build import build
from .config import load_layers
from .doctor import inspect
from .errors import ArmyError
from .models import resolve
from .paths import army_home, find_project
from .registry import Registry
from .routing import route


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ArmyError(message)


def parser() -> Parser:
    p = Parser(prog="army", description="Agent-Army core, skills, and shared local knowledge/memory. Supervised jobs; no unattended auto mode.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--resources", type=Path, help="Custom resource root containing registry/ and prompts/")
    p.add_argument("--config", type=Path, action="append", default=[], help="Extra model config layer; repeat in precedence order")
    p.add_argument("--project", type=Path, help="Existing Army project root")
    p.add_argument("--isolated", action="store_true", help="Ignore discovered user/project configuration")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("version")
    agents = commands.add_parser("agents").add_subparsers(dest="operation", required=True)
    agents.add_parser("list")
    agents.add_parser("validate")
    b = agents.add_parser("build")
    b.add_argument("--host", choices=("claude", "codex", "both"), default="both")
    b.add_argument("--tier", choices=("light", "medium", "heavy"))
    b.add_argument("--output", type=Path, required=True)
    m = commands.add_parser("models").add_subparsers(dest="operation", required=True).add_parser("resolve")
    m.add_argument("--agent", required=True)
    m.add_argument("--host", choices=("claude", "codex"), required=True)
    m.add_argument("--tier", choices=("light", "medium", "heavy"))
    m.add_argument("--model", help="Task preview override; grants no permission")
    m.add_argument("--effort")
    r = commands.add_parser("route")
    r.add_argument("task")
    r.add_argument("--agent")
    r.add_argument("--task-type")
    skills = commands.add_parser("skills").add_subparsers(dest="operation", required=True)
    for operation in ("list", "refresh", "resolve", "doctor"):
        s = skills.add_parser(operation)
        s.add_argument("--host", choices=("claude", "codex"), required=True)
        s.add_argument("--root", type=Path, action="append", default=[], help="Explicit permitted skill root; repeatable")
        s.add_argument("--plugin-index", type=Path, action="append", default=[], help="Opt-in Claude installed plugin index")
        if operation == "resolve":
            s.add_argument("--agent", required=True)
            s.add_argument("--task", required=True)
            s.add_argument("--pin", action="append", default=[], help="User-selected skill ID, exact path or unique name")
            s.add_argument("--require", action="append", default=[], help="Required capability")
            s.add_argument("--tool-capability", action="append", default=[], help="Capability supplied by available host tools")
            s.add_argument("--max-selected", type=int)
    from .knowledge_cli import add_parsers
    add_parsers(commands)
    from .jobs_cli import add_parsers as add_jobs
    add_jobs(commands)
    from .deployment_cli import add_parsers as add_deployment
    add_deployment(commands)
    commands.add_parser("doctor")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_output = "--json" in argv
    argv = [arg for arg in argv if arg != "--json"]
    try:
        options = parser().parse_args(argv)
        if options.command == "version":
            data = {"version": __version__}
        else:
            registry = Registry(options.resources)
            paths = []
            if not options.isolated:
                global_config = (getattr(options, "home", None) or army_home()) / "config.toml"
                if global_config.exists():
                    paths.append(global_config)
                project = options.project.resolve() if options.project else find_project(Path.cwd())
                if project:
                    project_config = project / ".agent-army" / "project.toml"
                    if project_config.is_file():
                        paths.append(project_config)
                    elif options.command not in ("skills", "store", "install"):
                        raise ArmyError(f"Not an initialized Army project: {project}")
            paths.extend(options.config)
            layers = load_layers(paths, set(registry.agents))
            if options.command == "agents":
                if options.operation == "list":
                    data = {"agents": [registry.agents[key].to_dict() for key in sorted(registry.agents)]}
                elif options.operation == "validate":
                    for agent in registry.agents:
                        for host in ("claude", "codex"):
                            for tier in ("light", "medium", "heavy"):
                                resolve(registry, agent, host, tier, layers)
                    data = {"valid": True, "agent_count": len(registry.agents), "scope": "static", "skills_required": False}
                else:
                    data = build(registry, options.output, options.host, options.tier, layers)
            elif options.command == "models":
                override = {k: v for k, v in {"model": options.model, "effort": options.effort}.items() if v is not None}
                data = resolve(registry, options.agent, options.host, options.tier, layers, override or None)
            elif options.command in ("store", "kb", "memory", "promotion"):
                from .knowledge_cli import run as run_knowledge
                data = run_knowledge(options)
            elif options.command in ("install", "migration"):
                from .deployment_cli import run as run_deployment
                data = run_deployment(options, registry, layers)
            elif options.command == "job":
                from .jobs_cli import run as run_jobs
                data = run_jobs(options)
            elif options.command == "skills":
                from .skills.commands import run
                data = run(options, layers, registry)
            elif options.command == "route":
                data = route(registry, options.task, options.agent, options.task_type)
            else:
                data = inspect(registry, layers)
        response, status = {"schema_version": 1, "ok": True, "data": data}, 0
    except ArmyError as exc:
        response, status = {"schema_version": 1, "ok": False, "error": {"code": exc.code, "message": str(exc)}}, exc.code
    except (OSError, UnicodeError) as exc:
        response, status = {"schema_version": 1, "ok": False, "error": {"code": 2, "message": str(exc)}}, 2
    if json_output:
        print(json.dumps(response, ensure_ascii=False))
    elif status:
        print(response["error"]["message"], file=sys.stderr)
    else:
        print(json.dumps(response["data"], indent=2, ensure_ascii=False))
    return status
