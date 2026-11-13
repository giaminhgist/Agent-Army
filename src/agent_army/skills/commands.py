from __future__ import annotations

import os
from pathlib import Path

from ..config import merge, only_keys
from ..errors import ArmyError
from .discovery import SkillRoot, claude_plugin_roots, default_roots, discover
from .metadata import validate_options
from .resolver import resolve_skills


def validate_settings(settings: dict) -> None:
    only_keys(settings, {"roots", "overrides", "max_selected"}, "skills")
    if "max_selected" in settings and (type(settings["max_selected"]) is not int or not 1 <= settings["max_selected"] <= 20):
        raise ArmyError("skills.max_selected must be an integer between 1 and 20")
    roots = settings.get("roots", [])
    if not isinstance(roots, list):
        raise ArmyError("skills.roots must be an array of tables")
    for root in roots:
        only_keys(root, {"path", "origin", "scope"}, "skill root")
        if not isinstance(root.get("path"), str) or not root["path"].strip():
            raise ArmyError("skill root.path is required")
        if "origin" in root and (not isinstance(root["origin"], str) or not root["origin"].strip()):
            raise ArmyError("skill root.origin must be nonempty text")
        if root.get("scope", "custom") not in ("user", "project", "custom", "plugin"):
            raise ArmyError("Unsupported skill root scope")
    overrides = settings.get("overrides", {})
    if not isinstance(overrides, dict):
        raise ArmyError("skills.overrides must be a table")
    for options in overrides.values():
        validate_options(options)


def collect(options, layers) -> dict:
    settings = {}
    for origin, config in layers:
        current = config.get("skills", {})
        # Config roots are relative to the containing config, not process cwd.
        current = merge({}, current)
        for root in current.get("roots", []):
            path = Path(root["path"]).expanduser()
            root["path"] = str(path if path.is_absolute() else Path(origin).parent / path)
        settings = merge(settings, current)
    roots = []
    project = options.project.resolve() if options.project else None
    if project and not project.is_dir():
        raise ArmyError(f"Project directory does not exist: {project}")
    if not options.isolated:
        if not project:
            from ..paths import find_project
            project = find_project(Path.cwd())
            if project is None:
                # Read-only discovery boundary may be a Git root even before Army initialization.
                project = next((p for p in (Path.cwd(), *Path.cwd().parents) if (p / ".git").exists()), Path.cwd())
        roots.extend(default_roots(options.host, project, cwd=Path.cwd()))
    for item in settings.get("roots", []):
        path = Path(item["path"]).expanduser().resolve()
        roots.append(SkillRoot(path, item.get("origin", "custom:" + str(path)), item.get("scope", "custom")))
    for path in options.root:
        path = path.expanduser().resolve()
        roots.append(SkillRoot(path, "custom:" + str(path)))
    extra_diagnostics = []
    for index in options.plugin_index:
        if options.host != "claude":
            raise ArmyError("--plugin-index is a Claude installed_plugins.json adapter; use --root for other plugin directories", 3)
        plugin_roots, diagnostics = claude_plugin_roots(index, project)
        roots.extend(plugin_roots)
        extra_diagnostics.extend(diagnostics)
    result = discover(roots, options.host, settings.get("overrides"))
    result["diagnostics"].extend(extra_diagnostics)
    result["max_selected"] = settings.get("max_selected", 3)
    return result


def run(options, layers, registry):
    inventory = collect(options, layers)
    if options.operation in ("list", "refresh"):
        return inventory
    if options.operation == "doctor":
        return {"host": options.host, "counts": {status: sum(s["eligibility"] == status for s in inventory["skills"])
                for status in ("declared_ready", "unknown", "unavailable")},
                "duplicate_names": inventory["duplicates"], "diagnostics": inventory["diagnostics"],
                "skills": inventory["skills"], "runtime_verified": False,
                "recommendations_required": False}
    return resolve_skills(inventory, registry, options.agent, options.task,
                          options.pin, options.require, options.tool_capability,
                          options.max_selected if options.max_selected is not None else inventory["max_selected"])
