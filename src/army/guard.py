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


SEPARATORS = SEPARATORS | {"(", ")", "{", "}", ";;"}
KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for", "in", "!", "case", "esac"}
WRAPPERS = {"time", "nohup", "nice", "exec", "command", "builtin", "env", "stdbuf", "timeout", "ionice"}
SUDO_ARG_FLAGS = {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}


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
    cwd: list[str] = []  # `cd` targets seen so far, applied in order
    seg: list[str] = []
    for tok in tokens + [";"]:
        if tok not in SEPARATORS:
            seg.append(tok)
            continue
        words = _strip_prefix(seg)
        seg = []
        if not words:
            continue
        if os.path.basename(words[0]) == "cd":
            cwd.append(words[1] if len(words) > 1 else os.path.expanduser("~"))
            continue

        def hit_here(p: str) -> str | None:
            return hit(os.path.join(*cwd, p) if cwd and not os.path.isabs(os.path.expanduser(p)) else p)

        if os.path.basename(words[0]) == "xargs":
            inner = _strip_prefix([w for w in words[1:] if not w.startswith("-")])
            if inner and os.path.basename(inner[0]) in WRITE_WORDS | {"sed"}:
                # the paths come from the rest of the pipeline: check every token of the command
                if r := next((r for t in tokens if t not in SEPARATORS and (r := hit_here(t))), None):
                    return r
            continue
        if r := _check_segment(words, hit_here):
            return r
    return None


def _strip_prefix(seg: list[str]) -> list[str]:
    """Drop shell keywords, VAR=value assignments and wrapper commands (sudo, time, nohup, env ...)."""
    w = list(seg)
    while w:
        head = w[0]
        if head in KEYWORDS or ("=" in head and not head.startswith(("-", "/", ".")) and head.split("=")[0].isidentifier()):
            w = w[1:]
        elif os.path.basename(head) == "sudo":
            w = w[1:]
            while w and w[0].startswith("-"):
                flag = w.pop(0)
                if flag in SUDO_ARG_FLAGS and w:
                    w.pop(0)
        elif os.path.basename(head) in WRAPPERS:
            w = w[1:]
            while w and w[0].startswith("-"):
                w.pop(0)
            if os.path.basename(head) == "timeout" and w:
                w.pop(0)  # the duration
        else:
            break
    return w


def _check_segment(words: list[str], hit) -> str | None:
    for i, tok in enumerate(words):
        if tok in REDIRECTS and i + 1 < len(words):
            if r := hit(words[i + 1]):
                return r
    words = [t for t in words if t not in REDIRECTS]
    if not words:
        return None
    prog = os.path.basename(words[0])
    args = [a for a in words[1:] if not a.startswith("-")]
    for i, a in enumerate(words[1:], 1):  # cp/mv/install -t DIR, --target-directory=DIR
        if prog in LAST_ARG | {"mv"}:
            if a == "-t" and i + 1 < len(words):
                if r := hit(words[i + 1]):
                    return r
            elif a.startswith("--target-directory="):
                if r := hit(a.split("=", 1)[1]):
                    return r
    if prog in ANY_ARG:
        return next((r for a in args if (r := hit(a))), None)
    if prog in LAST_ARG and args:
        return hit(args[-1])
    if prog == "sed" and any(a.startswith("-i") or a.startswith("--in-place") for a in words[1:]):
        return next((r for a in args if (r := hit(a))), None)
    if prog == "dd":
        return next((r for a in args if a.startswith("of=") and (r := hit(a[3:]))), None)
    if prog == "find" and ("-delete" in words or any(w in ("-exec", "-execdir") for w in words)):
        starts = []
        for a in words[1:]:
            if a.startswith("-") or a in ("(", "!"):
                break
            starts.append(a)
        if "-delete" in words or any(os.path.basename(w) in ANY_ARG for w in words):
            return next((r for a in starts if (r := hit(a))), None)
    return None


def _abs(base: Path, p: str) -> Path:
    q = Path(os.path.expanduser(p))
    if not q.is_absolute():
        q = Path(base) / q
    return Path(os.path.normpath(q))
