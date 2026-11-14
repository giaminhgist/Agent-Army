"""H4: deny tool calls that would write into a declared raw-data directory."""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

ANY_ARG = {"rm", "rmdir", "unlink", "shred", "truncate", "touch", "chmod", "chown", "mkdir", "ln", "tee", "mv"}
LAST_ARG = {"cp", "rsync", "install"}
WRITE_WORDS = ANY_ARG | LAST_ARG | {"sed", "dd", ">"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>", "1>", "2>"}
SEPARATORS = {";", "&&", "||", "|", "&", "\n"}
FILE_TOOLS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path", "NotebookEdit": "notebook_path"}
PATCH_RE = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+)$", re.M)


def check(payload: dict, project_root: Path, raw_dirs: list[str]) -> str | None:
    if not raw_dirs:
        return None
    cwd = Path(payload.get("cwd") or project_root)
    raws = [_abs(project_root, r) for r in raw_dirs]
    tool = payload.get("tool_name", "")
    ti = payload.get("tool_input") or {}

    def hit(p: str) -> str | None:
        target = _abs(cwd, p)
        for raw in raws:
            if target == raw or raw in target.parents:
                return f"Agent-Army: {p} is inside raw data dir {raw}; raw data is read-only."
        return None

    if tool in FILE_TOOLS:
        p = ti.get(FILE_TOOLS[tool])
        return hit(p) if p else None
    if tool == "apply_patch":
        for p in PATCH_RE.findall(str(ti.get("command", ""))):
            if r := hit(p.strip()):
                return r
        return None
    if tool == "Bash":
        return _check_bash(str(ti.get("command", "")), hit, raws, raw_dirs)
    return None


def _check_bash(cmd: str, hit, raws: list[Path], raw_dirs: list[str]) -> str | None:
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        words = set(re.findall(r"[\w>]+", cmd))
        if words & WRITE_WORDS:
            for raw_s, raw in zip(raw_dirs, raws):
                if raw_s in cmd or str(raw) in cmd:
                    return f"Agent-Army: command may write inside raw data dir {raw}; raw data is read-only."
        return None
    seg: list[str] = []
    for tok in tokens + [";"]:
        if tok in SEPARATORS:
            if r := _check_segment(seg, hit):
                return r
            seg = []
        else:
            seg.append(tok)
    return None


def _check_segment(seg: list[str], hit) -> str | None:
    if not seg:
        return None
    # redirections anywhere in the segment
    for i, tok in enumerate(seg):
        if tok in REDIRECTS and i + 1 < len(seg):
            if r := hit(seg[i + 1]):
                return r
    words = [t for t in seg if t not in REDIRECTS]
    while words and ("=" in words[0] and not words[0].startswith("-")) or (words and words[0] in ("sudo", "env", "command")):
        words = words[1:]
    if not words:
        return None
    prog = os.path.basename(words[0])
    args = [a for a in words[1:] if not a.startswith("-")]
    if prog in ANY_ARG:
        return next((r for a in args if (r := hit(a))), None)
    if prog in LAST_ARG and args:
        return hit(args[-1])
    if prog == "sed" and any(a.startswith("-i") or a.startswith("--in-place") for a in words[1:]):
        return next((r for a in args if (r := hit(a))), None)
    if prog == "dd":
        return next((r for a in args if a.startswith("of=") and (r := hit(a[3:]))), None)
    return None


def _abs(base: Path, p: str) -> Path:
    q = Path(os.path.expanduser(p))
    if not q.is_absolute():
        q = Path(base) / q
    return Path(os.path.normpath(q))
