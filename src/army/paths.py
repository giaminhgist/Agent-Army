"""Where Agent-Army keeps things: global store ($ARMY_HOME) and per-project stores."""

from __future__ import annotations

import os
from pathlib import Path

STATE_NAME = ".agent-army"
PROJECT_MARKER = "project.toml"


def army_home() -> Path:
    env = os.environ.get("ARMY_HOME")
    return Path(env).expanduser() if env else Path.home() / STATE_NAME


def state_dir(project: Path) -> Path:
    return Path(project) / STATE_NAME


def find_project(start: Path | None = None) -> Path | None:
    """First dir at or above `start` holding `.agent-army/project.toml`, never the global store."""
    home_store = _resolve(army_home())
    here = _resolve(Path(start) if start else Path.cwd())
    for d in (here, *here.parents):
        st = d / STATE_NAME
        if _resolve(st) == home_store:
            continue
        if (st / PROJECT_MARKER).is_file():
            return d
    return None


def scope_dir(scope: str, project: Path | None) -> Path:
    if scope == "global":
        return army_home()
    if scope == "project":
        if project is None:
            raise ValueError("project scope needs a project")
        return state_dir(project)
    raise ValueError(f"unknown scope: {scope}")


def _resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p.absolute()
