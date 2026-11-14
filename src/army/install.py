"""Install / uninstall Agent-Army for Claude Code and/or Codex, and redeploy after editing army.toml.

Writes only: $ARMY_HOME (app, launcher, stores), ~/.local/bin/army (symlink), the agents and `army` skill
for each platform, Agent-Army hook groups in ~/.claude/settings.json / ~/.codex/hooks.json, and one marked
block in ~/.claude/CLAUDE.md / ~/.codex/AGENTS.md. Everything is listed in install-manifest.json.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from army import __version__, build, config, paths

SOURCE = Path(__file__).resolve().parents[2]  # repo checkout or installed app dir (same layout)
EVENTS = {"SessionStart": "session-start", "Stop": "stop", "PreToolUse": "pre-tool-use", "PreCompact": "pre-compact"}
PRE_TOOL_MATCHER = {"claude": "Write|Edit|MultiEdit|NotebookEdit|Bash", "codex": "Bash|apply_patch"}
START, END = "<!-- agent-army:start -->", "<!-- agent-army:end -->"
INSTRUCTIONS = ("Agent-Army is installed. In a project with `.agent-army/`, its memory is injected at session start. "
                "Search knowledge with `army kb search \"<query>\"`, save with `army kb add` / `army mem add`, and use "
                "the `army` skill for multi-step research or engineering goals.")


# ---- locations ------------------------------------------------------------------------------------------------
def app_dir() -> Path:
    return paths.army_home() / "app"


def launcher() -> Path:
    return paths.army_home() / "bin" / "army"


def targets(platform: str) -> dict[str, Path]:
    h = Path.home()
    if platform == "claude":
        return {"agents": h / ".claude/agents", "skill": h / ".claude/skills/army",
                "hooks": h / ".claude/settings.json", "md": h / ".claude/CLAUDE.md"}
    return {"agents": h / ".codex/agents", "skill": h / ".agents/skills/army",
            "hooks": h / ".codex/hooks.json", "md": h / ".codex/AGENTS.md"}


def manifest_path() -> Path:
    return paths.army_home() / "install-manifest.json"


def read_manifest() -> dict:
    try:
        return json.loads(manifest_path().read_text())
    except (OSError, ValueError):
        return {}


# ---- json hook files -----------------------------------------------------------------------------------------
def _is_army_group(group: dict) -> bool:
    marker = f"{launcher()} hook"
    return any(marker in str(h.get("command", "")) for h in group.get("hooks", []) if isinstance(h, dict))


def _load_json(f: Path) -> dict:
    if not f.is_file() or not f.read_text().strip():
        return {}
    return json.loads(f.read_text())


def strip_hooks(f: Path) -> None:
    if not f.is_file():
        return
    data = _load_json(f)
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return
    for ev in list(hooks):
        groups = [g for g in hooks[ev] if not (isinstance(g, dict) and _is_army_group(g))]
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]
    if not hooks:
        del data["hooks"]
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def add_hooks(f: Path, platform: str) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.is_file():
        bak = f.with_name(f.name + ".army-bak")
        if not bak.exists():
            shutil.copy2(f, bak)
    strip_hooks(f)
    data = _load_json(f)
    hooks = data.setdefault("hooks", {})
    for ev, name in EVENTS.items():
        group: dict = {"hooks": [{"type": "command", "command": f"{launcher()} hook {name} --platform {platform}",
                                  "timeout": 30}]}
        if ev == "PreToolUse":
            group = {"matcher": PRE_TOOL_MATCHER[platform], **group}
        hooks.setdefault(ev, []).append(group)
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# ---- instruction block -----------------------------------------------------------------------------------------
def strip_block(f: Path) -> None:
    if not f.is_file():
        return
    text = f.read_text()
    while START in text and END in text:
        a, b = text.index(START), text.index(END) + len(END)
        text = text[:a].rstrip("\n") + ("\n" if text[:a].strip() else "") + text[b:].lstrip("\n")
    f.write_text(text)


def add_block(f: Path) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    strip_block(f)
    text = f.read_text() if f.is_file() else ""
    sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    f.write_text(f"{text}{sep}{START}\n{INSTRUCTIONS}\n{END}\n")


# ---- deploy --------------------------------------------------------------------------------------------------
def _copy_app() -> None:
    app = app_dir()
    if app.resolve() == SOURCE.resolve():
        return
    if app.exists():
        shutil.rmtree(app)
    app.mkdir(parents=True)
    shutil.copytree(SOURCE / "src" / "army", app / "src" / "army",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(SOURCE / "prompts", app / "prompts")
    shutil.copy2(SOURCE / "army.toml", app / "army.toml")


def _write_launcher() -> None:
    lp = launcher()
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(f'#!/bin/sh\nPYTHONPATH="{app_dir() / "src"}" exec "{sys.executable}" -m army "$@"\n')
    lp.chmod(0o755)
    link = Path.home() / ".local/bin/army"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() and str(paths.army_home()) in os.readlink(link):
        link.unlink()
    if not link.exists() and not link.is_symlink():
        link.symlink_to(lp)
    elif not link.is_symlink():
        print(f"  ! {link} exists and is not ours; left alone. Use {lp} directly.")


def deploy(platforms: list[str]) -> list[str]:
    """Render from $ARMY_HOME/army.toml + app prompts and copy into each platform. Returns written files."""
    cfg = config.load_config(paths.army_home() / "army.toml")
    out = build.build_all(cfg, app_dir() / "prompts", app_dir() / "build")
    written: list[str] = []
    for p in platforms:
        t = targets(p)
        t["agents"].mkdir(parents=True, exist_ok=True)
        for old in t["agents"].glob("army-*.md" if p == "claude" else "army_*.toml"):
            old.unlink()
        for f in out[f"{p}_agents"]:
            dst = t["agents"] / f.name
            shutil.copy2(f, dst)
            written.append(str(dst))
        t["skill"].mkdir(parents=True, exist_ok=True)
        dst = t["skill"] / "SKILL.md"
        shutil.copy2(out[f"{p}_skill"][0], dst)
        written.append(str(dst))
    return written


def redeploy() -> None:
    platforms = read_manifest().get("platforms", [])
    if not platforms:
        raise SystemExit("Agent-Army is not installed. Run install.py first.")
    files = deploy(platforms)
    man = read_manifest()
    man["files"] = sorted(set(files))
    manifest_path().write_text(json.dumps(man, indent=2) + "\n")


def install(platforms: list[str]) -> None:
    home = paths.army_home()
    for d in ("knowledge", "memory"):
        (home / d).mkdir(parents=True, exist_ok=True)
    _copy_app()
    if not (home / "army.toml").is_file():
        shutil.copy2(app_dir() / "army.toml", home / "army.toml")
    _write_launcher()
    files = deploy(platforms)
    for p in platforms:
        add_hooks(targets(p)["hooks"], p)
        add_block(targets(p)["md"])
    prev = read_manifest().get("platforms", [])
    man = {"version": __version__, "platforms": sorted(set(prev) | set(platforms)),
           "files": sorted(set(files)), "app": str(app_dir())}
    manifest_path().write_text(json.dumps(man, indent=2) + "\n")


def uninstall(purge: bool) -> None:
    man = read_manifest()
    for f in man.get("files", []):
        Path(f).unlink(missing_ok=True)
    for p in ("claude", "codex"):
        t = targets(p)
        for old in t["agents"].glob("army-*.md" if p == "claude" else "army_*.toml"):
            old.unlink()
        if t["skill"].is_dir():
            shutil.rmtree(t["skill"])
        try:
            strip_hooks(t["hooks"])
        except ValueError:
            print(f"  ! could not parse {t['hooks']}; remove Agent-Army hooks by hand.")
        strip_block(t["md"])
    link = Path.home() / ".local/bin/army"
    if link.is_symlink() and str(paths.army_home()) in os.readlink(link):
        link.unlink()
    home = paths.army_home()
    if purge:
        shutil.rmtree(home, ignore_errors=True)
        return
    for d in ("app", "bin"):
        shutil.rmtree(home / d, ignore_errors=True)
    manifest_path().unlink(missing_ok=True)


# ---- entry point ---------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="install.py", description="Install Agent-Army for Claude Code and/or Codex.")
    ap.add_argument("--claude", action="store_true", help="install for Claude Code")
    ap.add_argument("--codex", action="store_true", help="install for Codex CLI")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--purge", action="store_true", help="with --uninstall: also delete global knowledge and memory")
    ap.add_argument("--dry-run", action="store_true", help="print what would happen, change nothing")
    a = ap.parse_args(argv)
    if sys.version_info < (3, 11):
        print("Agent-Army needs Python ≥ 3.11.")
        return 1
    home = paths.army_home()
    if a.uninstall:
        if a.dry_run:
            print(f"dry-run: would remove Agent-Army agents, skills, hooks and instruction blocks; "
                  f"{'delete' if a.purge else 'keep'} {home}")
            return 0
        uninstall(a.purge)
        print("Agent-Army uninstalled." + ("" if a.purge else f" Knowledge and memory kept in {home}."))
        return 0
    platforms = [p for p in ("claude", "codex") if getattr(a, p)] or \
        [p for p in ("claude", "codex") if shutil.which(p)]
    if not platforms:
        print("Neither `claude` nor `codex` found on PATH; pass --claude and/or --codex.")
        return 1
    if a.dry_run:
        print(f"dry-run: platforms = {', '.join(platforms)}")
        print(f"  copy app → {app_dir()}; launcher → {launcher()}; symlink ~/.local/bin/army")
        print(f"  config  → {home / 'army.toml'} (only if missing)")
        for p in platforms:
            t = targets(p)
            print(f"  [{p}] 9 agents → {t['agents']}; skill → {t['skill']}; hooks → {t['hooks']}; block → {t['md']}")
        return 0
    install(platforms)
    print(f"Agent-Army installed for: {', '.join(platforms)}")
    if str(Path.home() / ".local/bin") not in os.environ.get("PATH", "").split(os.pathsep):
        print("  ! ~/.local/bin is not on PATH; add it so `army` works in your shell.")
    if "codex" in platforms:
        print("  → In Codex, run /hooks once to trust the Agent-Army hooks.")
    from army import doctor
    print(doctor.report(doctor.run_checks(platforms)))
    return 0
