"""`army init`: the per-project store and its settings (raw-data and sensitive dirs)."""

from __future__ import annotations

import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from army import paths

PLAN_TEMPLATE = "# Plan\n\n| Task | Agent | Output | Done when | Status |\n|---|---|---|---|---|\n"


def _rel(root: Path, d: str) -> str:
    p = Path(d).expanduser()
    if p.is_absolute():
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix().rstrip("/") or "."


def _merge(old: list[str], new: list[str]) -> list[str]:
    out = list(old)
    for x in new:
        if x not in out:
            out.append(x)
    return out


def load_project(root: Path) -> dict:
    f = paths.state_dir(root) / paths.PROJECT_MARKER
    with open(f, "rb") as fh:
        return tomllib.load(fh)


def init_project(root: Path, raw_dirs: list[str], sensitive_dirs: list[str]) -> Path:
    root = Path(root)
    st = paths.state_dir(root)
    if st.resolve() == paths.army_home().resolve():
        raise ValueError(f"{st} is the Agent-Army global store; run `army init` inside a project directory instead.")
    for d in ("knowledge", "memory", "runs"):
        (st / d).mkdir(parents=True, exist_ok=True)
    marker = st / paths.PROJECT_MARKER
    cfg = {"name": root.resolve().name, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "raw_dirs": [], "sensitive_dirs": []}
    if marker.is_file():
        cfg.update(load_project(root))
    cfg["raw_dirs"] = _merge(cfg.get("raw_dirs", []), [_rel(root, d) for d in raw_dirs])
    cfg["sensitive_dirs"] = _merge(cfg.get("sensitive_dirs", []), [_rel(root, d) for d in sensitive_dirs])
    marker.write_text(
        "# Agent-Army project settings\n"
        f"name = {json.dumps(cfg['name'], ensure_ascii=False)}\n"
        f"created = {json.dumps(str(cfg['created']))}\n"
        "# Read-only: agents and the guard hook never write here.\n"
        f"raw_dirs = {json.dumps(cfg['raw_dirs'], ensure_ascii=False)}\n"
        "# Never send contents of these dirs to external services.\n"
        f"sensitive_dirs = {json.dumps(cfg['sensitive_dirs'], ensure_ascii=False)}\n",
        encoding="utf-8")
    plan = st / "plan.md"
    if not plan.exists():
        plan.write_text(PLAN_TEMPLATE, encoding="utf-8")
    return st
