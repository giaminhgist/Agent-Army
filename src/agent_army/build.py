from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import __version__
from .adapters import claude, codex
from .adapters.base import digest
from .errors import ArmyError
from .models import resolve
from .paths import contained
from .registry import Registry


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".army-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build(registry: Registry, output: Path, host: str = "both", tier: str | None = None, layers=None) -> dict:
    output = output.resolve()
    if any(part.lower() in {".claude", ".codex", ".agents", ".agent-army"} for part in output.parts):
        raise ArmyError("Build is staging-only; native host and state directories are not build targets")
    if output == registry.root or output.is_relative_to(registry.root):
        raise ArmyError("Build output cannot overwrite source resources")
    hosts = ("claude", "codex") if host == "both" else (host,)
    rendered, profiles = {}, []
    for selected in hosts:
        if selected not in ("claude", "codex"):
            raise ArmyError(f"Unsupported host: {selected}", 3)
        for agent in sorted(registry.agents):
            profile = resolve(registry, agent, selected, tier, layers)
            adapter, ext = (claude, "md") if selected == "claude" else (codex, "toml")
            rendered[f"{selected}/agents/army-{agent}.{ext}"] = adapter.render(registry, agent, profile)
            profiles.append(profile)
    manifest_path = contained(output, "manifest.json")
    previous = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise ArmyError("Invalid previous build manifest", 5) from exc
        if not isinstance(previous, dict) or previous.get("owner") != "agent-army" or not isinstance(previous.get("files"), dict):
            raise ArmyError("Output has an unrecognized manifest", 5)
    ownership = dict(previous.get("files", {}))
    # Preflight every destination before writing any generated file.
    for relative in rendered:
        target = contained(output, relative)
        if target.exists() and (not target.is_file() or ownership.get(relative) != digest(target.read_text(encoding="utf-8"))):
            raise ArmyError(f"Unowned or edited output: {target}", 5)
    for relative, text in rendered.items():
        atomic_write(contained(output, relative), text)
        ownership[relative] = digest(text)
    manifest = {"schema_version": 1, "owner": "agent-army", "renderer_version": __version__, "files": dict(sorted(ownership.items()))}
    atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {"output": str(output), "generated_count": len(rendered), "files": sorted(rendered), "profiles": profiles,
            "installed": False, "host_runtime_verified": False}
