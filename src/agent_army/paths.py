from __future__ import annotations

import os
from pathlib import Path

from .errors import ArmyError


def army_home() -> Path:
    return Path(os.environ.get("AGENT_ARMY_HOME", str(Path.home() / ".agent-army"))).expanduser().resolve()


def contained(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if Path(relative).is_absolute() or not candidate.is_relative_to(root.resolve()):
        raise ArmyError(f"Path escapes resource root: {relative}")
    return candidate


def find_project(start: Path) -> Path | None:
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / ".agent-army" / "project.toml").is_file():
            return folder
        if folder == Path.home().resolve():
            break
    return None
