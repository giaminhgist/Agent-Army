"""H11: `army doctor` — is everything installed and wired, and which recommended skills are missing."""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from army import build, config, paths


@dataclass
class Check:
    status: str  # OK | WARN | FAIL
    name: str
    detail: str


def _skill_roots(platform: str) -> tuple[list[Path], list[Path]]:
    h = Path.home()
    if platform == "claude":
        return [h / ".claude/skills"], [h / ".claude/plugins/cache"]
    return [h / ".agents/skills", h / ".codex/skills"], [h / ".codex/plugins/cache"]


def find_skill(name: str, platform: str) -> Path | None:
    direct, caches = _skill_roots(platform)
    for root in direct:
        p = root / name / "SKILL.md"
        if p.is_file():
            return p
    for cache in caches:
        if cache.is_dir():
            for p in cache.glob(f"**/skills/{name}/SKILL.md"):
                return p
    return None


def manifest() -> dict:
    f = paths.army_home() / "install-manifest.json"
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {}


def installed_platforms() -> list[str]:
    return list(manifest().get("platforms", []))


def _fts5_ok() -> bool:
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        con.close()
        return True
    except sqlite3.Error:
        return False


def _hooks_registered(platform: str) -> bool:
    f = Path.home() / (".claude/settings.json" if platform == "claude" else ".codex/hooks.json")
    try:
        return f"{paths.army_home() / 'bin' / 'army'} hook" in f.read_text()
    except OSError:
        return False


def run_checks(platforms: list[str]) -> list[Check]:
    cfg = config.load_config()
    names = config.agent_names(cfg)
    out = [
        Check("OK" if sys.version_info >= (3, 11) else "FAIL", "python", sys.version.split()[0] + " (need ≥ 3.11)"),
        Check("OK" if _fts5_ok() else "FAIL", "sqlite fts5", "available" if _fts5_ok() else "missing"),
        Check("OK" if paths.army_home().is_dir() else "FAIL", "army home", str(paths.army_home())),
        Check("OK" if shutil.which("army") else "WARN", "army on PATH",
              shutil.which("army") or "not found — add ~/.local/bin to PATH"),
    ]
    h = Path.home()
    for p in platforms:
        adir = h / (".claude/agents" if p == "claude" else ".codex/agents")
        ext = "md" if p == "claude" else "toml"
        missing = [n for n in names if not (adir / f"{build.agent_id(n, p)}.{ext}").is_file()]
        out.append(Check("FAIL" if missing else "OK", f"{p} agents",
                         f"missing: {', '.join(missing)}" if missing else f"{len(names)} in {adir}"))
        sk = h / (".claude/skills/army/SKILL.md" if p == "claude" else ".agents/skills/army/SKILL.md")
        out.append(Check("OK" if sk.is_file() else "FAIL", f"{p} army skill", str(sk)))
        out.append(Check("OK" if _hooks_registered(p) else "WARN", f"{p} hooks",
                         "registered" if _hooks_registered(p) else "not registered — re-run install.py"))
        if p == "codex":
            out.append(Check("WARN", "codex hook trust", "Trust the hooks once in Codex with /hooks"))
    for p in (platforms or ["claude", "codex"]):
        need: dict[str, list[str]] = {}
        for n in names:
            for s in cfg["agents"][n]["skills"]:
                need.setdefault(s, []).append(n)
        missing = [f"{s} ({', '.join(a)})" for s, a in need.items() if find_skill(s, p) is None]
        out.append(Check("WARN" if missing else "OK", f"recommended skills [{p}]",
                         ("missing: " + "; ".join(missing)) if missing else "all installed"))
    return out


def report(checks: list[Check]) -> str:
    return "\n".join(f"{'[' + c.status + ']':<7}{c.name} — {c.detail}" for c in checks)
