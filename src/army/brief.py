"""The session brief injected at session start (and printed by `army mem brief`)."""

from __future__ import annotations

from pathlib import Path

from army import paths, store


def open_tasks(project: Path) -> list[str]:
    plan = paths.state_dir(project) / "plan.md"
    if not plan.is_file():
        return []
    out = []
    for line in plan.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("- [ ]"):
            out.append(s[5:].strip())
        elif s.startswith("|") and s.rstrip("|").rstrip().lower().endswith(("todo", "in_progress", "in progress", "open")):
            out.append(s)
    return out


def brief(project: Path | None, max_chars: int = 4000) -> str:
    sections: list[str] = []
    pending_n = 0
    if project is not None:
        tasks = open_tasks(project)
        if tasks:
            sections.append("## Open tasks\n" + "\n".join(f"- {t}" for t in tasks))
        decisions = store.load_items("project", project, "decision")[:10]
        if decisions:
            sections.append("## Recent decisions\n" + "\n".join(f"- {_line(i)}" for i in decisions))
        progress = [f"- {_line(i)}" for i in store.load_items("project", project, "progress")[:3]]
        snap = paths.state_dir(project) / "snapshot.md"
        if snap.is_file():
            progress.append("\n" + snap.read_text(encoding="utf-8", errors="replace").strip())
        if progress:
            sections.append("## Progress\n" + "\n".join(progress))
        pending_n = sum(1 for i in store.load_items("project", project) if i.meta.get("promote") == "pending")
    glob = [i for i in store.load_items("global") if i.type in ("lesson", "preference")][:10]
    if glob:
        sections.append("## Global lessons & preferences\n" + "\n".join(f"- [{i.type}] {i.title}" for i in glob))
    if not sections and not pending_n:
        return ""
    text = "# Agent-Army memory\n\n" + "\n\n".join(sections)
    if pending_n:
        text += f"\n\n{pending_n} item(s) pending promotion → army promote --pick"
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text


def _line(item: store.Item) -> str:
    body = " ".join(item.body.split())
    return item.title if not body or body == item.title else f"{item.title} — {body[:200]}"
