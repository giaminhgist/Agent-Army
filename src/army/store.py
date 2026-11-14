"""Knowledge and memory items: one markdown file with frontmatter per item."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from army import frontmatter, paths

KNOWLEDGE_TYPES = ("paper", "note")
MEMORY_TYPES = ("decision", "progress", "lesson", "preference")
TYPES = KNOWLEDGE_TYPES + MEMORY_TYPES
PENDING_BY_DEFAULT = ("paper", "note", "lesson", "preference")


@dataclass
class Item:
    id: str
    type: str
    title: str
    scope: str
    path: Path
    meta: dict
    body: str


def type_dir(scope: str, type: str, project: Path | None) -> Path:
    sub = "knowledge" if type in KNOWLEDGE_TYPES else "memory"
    return paths.scope_dir(scope, project) / sub


def slug(text: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    ascii_ = ascii_.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_).strip("-").lower()
    return s or "item"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def add_item(scope: str, type: str, title: str, body: str, tags=(), source: str = "",
             project: Path | None = None) -> Item:
    if type not in TYPES:
        raise ValueError(f"unknown type: {type} (expected one of {', '.join(TYPES)})")
    title = " ".join(title.split()) or "untitled"
    created = now_iso()
    item_id = f"{type}-{slug(title)[:40]}-{hashlib.sha1((title + created).encode()).hexdigest()[:6]}"
    meta = {"id": item_id, "type": type, "title": title, "tags": list(tags), "source": source,
            "created": created, "scope": scope}
    if scope == "project":
        meta["origin_project"] = str(project)
        meta["promote"] = "pending" if type in PENDING_BY_DEFAULT else "no"
    d = type_dir(scope, type, project)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{item_id}.md"
    path.write_text(frontmatter.dump(meta, body.rstrip("\n") + "\n"), encoding="utf-8")
    return Item(item_id, type, title, scope, path, meta, body)


def read_item(path: Path, scope: str) -> Item | None:
    try:
        meta, body = frontmatter.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    if "id" not in meta:
        return None
    return Item(meta["id"], meta.get("type", "note"), meta.get("title", meta["id"]), scope, path, meta, body)


def item_files(scope: str, project: Path | None) -> list[Path]:
    base = paths.scope_dir(scope, project)
    out: list[Path] = []
    for sub in ("knowledge", "memory"):
        d = base / sub
        if d.is_dir():
            out.extend(sorted(d.glob("*.md")))
    return out


def load_items(scope: str, project: Path | None = None, type: str | None = None) -> list[Item]:
    items = [i for p in item_files(scope, project) if (i := read_item(p, scope))]
    if type:
        items = [i for i in items if i.type == type]
    return sorted(items, key=lambda i: str(i.meta.get("created", "")), reverse=True)


def get_item(item_id: str, scope: str, project: Path | None = None) -> Item | None:
    for sub in ("knowledge", "memory"):
        p = paths.scope_dir(scope, project) / sub / f"{item_id}.md"
        if p.is_file():
            return read_item(p, scope)
    return None


def update_meta(item: Item, **changes) -> Item:
    item.meta.update(changes)
    item.path.write_text(frontmatter.dump(item.meta, item.body), encoding="utf-8")
    return item
