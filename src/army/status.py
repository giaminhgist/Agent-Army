"""H10: one-screen project status."""

from __future__ import annotations

from pathlib import Path

from army import brief, promote, runlog


def status_text(project: Path) -> str:
    lines = [f"Project: {project.name}  ({project})", ""]
    tasks = brief.open_tasks(project)
    lines.append("Open tasks:" if tasks else "Open tasks: none")
    lines += [f"  - {t}" for t in tasks]
    runs = runlog.recent(project, 5)
    lines.append("")
    lines.append("Recent runs:" if runs else "Recent runs: none")
    lines += [f"  {r.get('run_id', '?')}  {r.get('status', '?'):<11} exit={r.get('exit_code', '-')}  {r.get('cmd', '')}" for r in runs]
    lines.append("")
    lines.append(f"Pending promotion: {len(promote.pending(project))}")
    return "\n".join(lines)
