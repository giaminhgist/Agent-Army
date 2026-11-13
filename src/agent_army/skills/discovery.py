from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from ..errors import ArmyError
from .metadata import SkillDescriptor, parser_module, read_skill, validate_options


@dataclass(frozen=True)
class SkillRoot:
    path: Path
    origin: str
    scope: str = "custom"


def default_roots(host: str, project: Path | None = None, home: Path | None = None,
                  cwd: Path | None = None) -> list[SkillRoot]:
    home = home or Path.home()
    claude_home = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
    roots = [SkillRoot(claude_home / "skills" if host == "claude" else home / ".agents/skills",
                       f"{host}:user", "user")]
    if project:
        project = project.resolve()
        current = (cwd or project).resolve()
        if not current.is_relative_to(project):
            current = project
        for directory in (current, *current.parents):
            roots.append(SkillRoot(directory / (".claude/skills" if host == "claude" else ".agents/skills"),
                                   f"{host}:project:{directory}", "project"))
            if directory == project:
                break
    return roots


def claude_plugin_roots(index: Path, project: Path | None) -> tuple[list[SkillRoot], list[dict]]:
    """Opt-in installed plugin index. Installed does not mean enabled in this session."""
    roots, diagnostics = [], []
    try:
        if index.stat().st_size > 4 * 1024 * 1024:
            raise ArmyError("Plugin index exceeds 4 MiB")
        data = json.loads(index.read_text(encoding="utf-8"))
        plugins = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(plugins, dict):
            raise ArmyError("Plugin index requires plugins mapping")
        for plugin_id, entries in plugins.items():
            if not isinstance(plugin_id, str) or not isinstance(entries, list):
                raise ArmyError("Invalid plugin entries")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ArmyError("Invalid plugin installation")
                scope = entry.get("scope")
                if scope not in ("user", "project", "local"):
                    diagnostics.append({"origin": plugin_id, "reason": "unsupported plugin scope"})
                    continue
                if scope != "user":
                    owner = entry.get("projectPath")
                    if not isinstance(owner, str) or not project or Path(owner).resolve() != project.resolve():
                        continue
                if entry.get("enabled") is False:
                    continue
                install = entry.get("installPath")
                if not isinstance(install, str) or not Path(install).is_absolute():
                    raise ArmyError("Plugin installPath must be absolute")
                roots.append(SkillRoot(Path(install) / "skills", f"claude-plugin:{plugin_id}", "plugin"))
        diagnostics.append({"path": str(index), "reason": "Plugin paths are candidates; host enabled/managed settings are not verified"})
    except (OSError, ValueError, ArmyError) as exc:
        diagnostics.append({"path": str(index), "reason": str(exc)})
    return roots, diagnostics


def evaluate(skill: SkillDescriptor, host: str, env=None, which=None) -> None:
    env = os.environ if env is None else env
    which = shutil.which if which is None else which
    reasons = []
    if not skill.enabled:
        reasons.append("disabled")
    if skill.hosts and host not in skill.hosts:
        reasons.append(f"incompatible host: {host}")
    reasons.extend(f"missing environment variable: {key}" for key in skill.requires_env if not env.get(key))
    reasons.extend(f"missing tool: {tool}" for tool in skill.requires_tools if which(tool) is None)
    skill.reasons = reasons
    skill.eligibility = "unavailable" if reasons else ("declared_ready" if skill.requirements_known else "unknown")


def discover(roots: list[SkillRoot], host: str, overrides: dict | None = None,
             env=None, which=None, max_files: int = 2000, max_dirs: int = 10000) -> dict:
    if host not in ("claude", "codex"):
        raise ArmyError(f"Unknown skill host: {host}", 3)
    parser_module()
    overrides = overrides or {}
    for options in overrides.values():
        validate_options(options)
    skills, diagnostics, seen = [], [], set()
    scanned, directories = 0, 0
    for source in roots:
        root = source.path.expanduser().resolve()
        if not root.exists():
            diagnostics.append({"path": str(root), "reason": "root does not exist"})
            continue
        if not root.is_dir():
            diagnostics.append({"path": str(root), "reason": "root is not a directory"})
            continue
        def walk_error(error):
            diagnostics.append({"path": str(root), "reason": f"walk failed: {type(error).__name__}"})
        for directory, subdirs, filenames in os.walk(root, followlinks=False, onerror=walk_error):
            directories += 1
            if directories > max_dirs:
                raise ArmyError("Skill scan directory limit exceeded; narrow roots", 3)
            parent = Path(directory)
            subdirs[:] = sorted(d for d in subdirs if d not in {".git", ".venv", "node_modules", "__pycache__"}
                                and not (parent / d).is_symlink()
                                and not getattr(parent / d, "is_junction", lambda: False)())
            if "SKILL.md" not in filenames:
                continue
            path = parent / "SKILL.md"
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                diagnostics.append({"path": str(path), "reason": "symlink escapes registered root"})
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            scanned += 1
            if scanned > max_files:
                raise ArmyError("Skill scan file limit exceeded; narrow roots", 3)
            try:
                skill = read_skill(path, source.origin, source.scope)
                # Exact identity or absolute path; never change all same-named skills accidentally.
                updates = overrides.get(skill.path, {}) | overrides.get(skill.id, {})
                for key, value in updates.items():
                    setattr(skill, "host_invocation" if key == "invocation" else key, value)
                if all(key in updates for key in ("dependencies", "requires_env", "requires_tools")):
                    skill.requirements_known = True
                evaluate(skill, host, env, which)
                skills.append(skill)
            except (ArmyError, OSError, UnicodeError) as exc:
                diagnostics.append({"path": str(path), "reason": str(exc)})
    by_name = {}
    for skill in skills:
        by_name.setdefault(skill.name, []).append(skill.id)
    matched = {s.id for s in skills} | {s.path for s in skills}
    diagnostics.extend({"override": key, "reason": "override did not match any skill"} for key in overrides if key not in matched)
    return {"schema_version": 1, "host": host,
            "roots": [{"path": str(r.path), "origin": r.origin, "scope": r.scope} for r in roots],
            "skills": [s.to_dict() for s in sorted(skills, key=lambda s: s.id)],
            "duplicates": {name: ids for name, ids in by_name.items() if len(ids) > 1},
            "diagnostics": diagnostics, "scanned_files": scanned,
            "cache": "none; every discovery re-reads metadata and hashes",
            "execution_authorized": False}
