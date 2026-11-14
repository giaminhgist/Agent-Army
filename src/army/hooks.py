"""Hook handlers shared by Claude Code and Codex (`army hook <event> --platform ...`).

Every handler fails open: an error never blocks the session or a tool call.
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

from army import paths

EVENTS = ("session-start", "stop", "pre-tool-use", "pre-compact")


def handle(event: str, platform: str, stdin_text: str) -> tuple[int, str, str]:
    try:
        if event not in EVENTS:
            return 0, "", ""
        payload = json.loads(stdin_text or "{}")
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        cwd = Path(payload.get("cwd") or Path.cwd())
        project = paths.find_project(cwd)
        return HANDLERS[event](payload, project, platform)
    except Exception:  # noqa: BLE001 — fail open by design
        _log_error(event, platform)
        return 0, "", ""


def _session_start(payload: dict, project: Path | None, platform: str) -> tuple[int, str, str]:
    from army import brief

    return 0, brief.brief(project), ""


def _stop(payload: dict, project: Path | None, platform: str) -> tuple[int, str, str]:
    from army import promote

    if project is None:
        return 0, "", ""
    n = len(promote.pending(project))
    mark = paths.state_dir(project) / ".stop-notified"
    try:
        last = int(mark.read_text().strip() or 0)
    except (OSError, ValueError):
        last = 0
    if n != last:
        mark.write_text(str(n))
    if n > last:
        msg = f"Agent-Army: {n} item(s) pending promotion to global — run `army promote --pick`."
        return 0, json.dumps({"systemMessage": msg}, ensure_ascii=False), ""
    return 0, "", ""


def _pre_tool_use(payload: dict, project: Path | None, platform: str) -> tuple[int, str, str]:
    from army import guard, project as proj

    if project is None:
        return 0, "", ""
    raw = proj.load_project(project).get("raw_dirs", [])
    reason = guard.check(payload, project, raw)
    return (2, "", reason) if reason else (0, "", "")


def _pre_compact(payload: dict, project: Path | None, platform: str) -> tuple[int, str, str]:
    from army import status

    if project is None:
        return 0, "", ""
    iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (paths.state_dir(project) / "snapshot.md").write_text(
        f"# Snapshot {iso}\n\n{status.status_text(project)}\n", encoding="utf-8")
    return 0, "", ""


HANDLERS = {"session-start": _session_start, "stop": _stop, "pre-tool-use": _pre_tool_use,
            "pre-compact": _pre_compact}


def _log_error(event: str, platform: str) -> None:
    try:
        home = paths.army_home()
        home.mkdir(parents=True, exist_ok=True)
        with open(home / "hook-errors.log", "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now(timezone.utc).isoformat(timespec='seconds')} {platform} {event}\n")
            f.write(traceback.format_exc())
    except Exception:  # noqa: BLE001
        pass
