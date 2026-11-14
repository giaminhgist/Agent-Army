"""Minimal frontmatter: `---` block of `key: value` lines. Values: str, int, bool, inline list of str."""

from __future__ import annotations

import json


def parse(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        if text.endswith("\n---"):
            end = len(text) - 4
        else:
            return {}, text
    head = text[4:end]
    body = text[end + 5:]
    meta: dict = {}
    for line in head.splitlines():
        if ": " not in line and not line.endswith(":"):
            continue
        key, _, raw = line.partition(":")
        meta[key.strip()] = _value(raw.strip())
    return meta, body


def dump(meta: dict, body: str) -> str:
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {_render(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def _render(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (list, tuple)):
        return json.dumps([str(x) for x in v], ensure_ascii=False)
    s = str(v).replace("\n", " ")
    # Quote strings that would otherwise read back as another type.
    if s in ("true", "false") or _is_int(s) or s.startswith("[") or s.startswith('"') or s != s.strip():
        return json.dumps(s, ensure_ascii=False)
    return s


def _value(raw: str):
    if raw == "true":
        return True
    if raw == "false":
        return False
    if _is_int(raw):
        return int(raw)
    if raw.startswith("[") or raw.startswith('"'):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _is_int(s: str) -> bool:
    return s.lstrip("-").isdigit() and s not in ("", "-")
