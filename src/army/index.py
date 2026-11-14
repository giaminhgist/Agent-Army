"""Full-text search over items with SQLite FTS5 (BM25), one index per store."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from army import paths, store

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(path TEXT PRIMARY KEY, mtime REAL);
-- v2: title/tags/body are stored with đ folded to d
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  path UNINDEXED, id, title, tags, body, tokenize="unicode61 remove_diacritics 2");
"""


@dataclass
class Hit:
    scope: str
    id: str
    title: str
    path: Path
    snippet: str
    score: float


def search(query: str, scope: str = "all", project: Path | None = None, limit: int = 10) -> list[Hit]:
    match = _match_expr(query)
    if not match:
        return []
    scopes = {"all": ["project", "global"], "project": ["project"], "global": ["global"]}[scope]
    hits: list[Hit] = []
    for sc in scopes:
        if sc == "project" and project is None:
            continue
        hits.extend(_search_one(sc, project, match, limit))
    return hits[:limit]


def _fold(text: str) -> str:
    # unicode61 strips combining marks but treats đ/Đ as a separate letter; fold it by hand.
    return text.replace("đ", "d").replace("Đ", "D")


def _match_expr(query: str) -> str:
    tokens = re.findall(r"\w+", _fold(query or ""))
    return " OR ".join(f'"{t}"' for t in tokens)


def _search_one(scope: str, project: Path | None, match: str, limit: int) -> list[Hit]:
    base = paths.scope_dir(scope, project)
    if not base.is_dir():
        return []
    db = base / "index.sqlite"
    for attempt in (1, 2):
        try:
            con = sqlite3.connect(db)
            try:
                con.executescript(SCHEMA)
                _refresh(con, scope, project)
                rows = con.execute(
                    "SELECT path, id, title, snippet(fts, 4, '[', ']', '…', 12), bm25(fts) "
                    "FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?", (match, limit)).fetchall()
                con.commit()
            finally:
                con.close()
            return [Hit(scope, r[1], r[2], Path(r[0]), r[3], r[4]) for r in rows]
        except sqlite3.OperationalError:
            raise  # e.g. "database is locked": never delete an index another process is using
        except sqlite3.DatabaseError:
            if attempt == 2:
                raise
            for suffix in ("", "-wal", "-shm", "-journal"):
                Path(str(db) + suffix).unlink(missing_ok=True)
    return []


def _refresh(con: sqlite3.Connection, scope: str, project: Path | None) -> None:
    known = dict(con.execute("SELECT path, mtime FROM docs").fetchall())
    seen = set()
    for p in store.item_files(scope, project):
        key = str(p)
        seen.add(key)
        mtime = p.stat().st_mtime
        if known.get(key) == mtime:
            continue
        item = store.read_item(p, scope)
        con.execute("DELETE FROM fts WHERE path = ?", (key,))
        if item:
            tags = item.meta.get("tags") or []
            con.execute("INSERT INTO fts(path, id, title, tags, body) VALUES (?,?,?,?,?)",
                        (key, item.id, _fold(item.title),
                         _fold(" ".join(tags) if isinstance(tags, list) else str(tags)), _fold(item.body)))
        con.execute("INSERT OR REPLACE INTO docs(path, mtime) VALUES (?,?)", (key, mtime))
    for key in set(known) - seen:
        con.execute("DELETE FROM fts WHERE path = ?", (key,))
        con.execute("DELETE FROM docs WHERE path = ?", (key,))
