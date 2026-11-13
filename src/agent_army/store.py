"""Versioned local SQLite stores, independent of Claude/Codex.

This is an API boundary, not protection against arbitrary same-user filesystem access.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .errors import ArmyError
from .paths import contained
from .routing import normalize

MAX_BODY = 4 * 1024 * 1024
STATUSES = {"active", "superseded", "deprecated", "revoked"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def expiry(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ArmyError("expires_at must be an ISO-8601 timestamp with timezone") from exc


def source_key(value: str) -> str:
    value = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "https://arxiv.org/abs/", "arxiv:"):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
    return value


def chunks(body: str):
    start = 0
    while start < len(body):
        end = min(start + 2000, len(body))
        if end < len(body):
            split = body.rfind("\n\n", start + 1000, end)
            if split > start:
                end = split
        headings = re.findall(r"(?m)^#{1,6}\s+(.+)$", body[:start])
        first_line = body[start:end].splitlines()[0] if body[start:end].splitlines() else ""
        current_heading = re.match(r"^#{1,6}\s+(.+)$", first_line)
        if current_heading:
            headings.append(current_heading[1])
        yield start, end, headings[-1] if headings else "", body[start:end]
        if end == len(body):
            break
        start = max(start + 1, end - 200)


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS items(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, revision INTEGER NOT NULL,
 title TEXT NOT NULL, status TEXT NOT NULL, expires_at TEXT,
 body_hash TEXT NOT NULL, fingerprint TEXT NOT NULL, metadata TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_fingerprint ON items(fingerprint);
CREATE TABLE IF NOT EXISTS versions(
 item_id TEXT NOT NULL, revision INTEGER NOT NULL, record TEXT NOT NULL,
 PRIMARY KEY(item_id,revision), FOREIGN KEY(item_id) REFERENCES items(id));
CREATE TABLE IF NOT EXISTS chunks(
 citation TEXT PRIMARY KEY, item_id TEXT NOT NULL, revision INTEGER NOT NULL,
 start_offset INTEGER NOT NULL, end_offset INTEGER NOT NULL, heading TEXT NOT NULL,
 text TEXT NOT NULL, FOREIGN KEY(item_id,revision) REFERENCES versions(item_id,revision));
CREATE TABLE IF NOT EXISTS source_keys(item_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
 PRIMARY KEY(item_id,key), FOREIGN KEY(item_id) REFERENCES items(id));
CREATE INDEX IF NOT EXISTS source_values ON source_keys(value);
CREATE TABLE IF NOT EXISTS events(
 id TEXT PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS promotions(
 id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, preview_hash TEXT NOT NULL,
 state TEXT NOT NULL, target_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS retained_items(item_id TEXT PRIMARY KEY, FOREIGN KEY(item_id) REFERENCES items(id));
CREATE TABLE IF NOT EXISTS promotion_links(
 id TEXT PRIMARY KEY, preview_hash TEXT NOT NULL, item_id TEXT NOT NULL,
 target_revision INTEGER NOT NULL, body_hash TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
 receipt TEXT NOT NULL, FOREIGN KEY(item_id) REFERENCES items(id));
"""


class Store:
    def __init__(self, root: Path, scope: str, project_id: str | None = None):
        if scope not in ("project", "global") or (scope == "project" and not project_id):
            raise ArmyError("Store requires global scope or project scope with identity")
        if scope == "global" and project_id is not None:
            raise ArmyError("Global store cannot have project identity")
        self.root = Path(root).resolve()
        if str(self.root).startswith("\\\\"):
            raise ArmyError("Network-share stores are unsupported", 3)
        self.scope, self.project_id = scope, project_id
        self.db_path = contained(self.root, "store.sqlite")

    @classmethod
    def initialize(cls, root: Path, scope: str, project_id: str | None = None, *, fts: bool = True):
        store = cls(root, scope, project_id)
        if store.db_path.exists():
            with store.connect():
                pass
            return store
        store.root.mkdir(parents=True, exist_ok=True)
        contained(store.root, "blobs").mkdir(exist_ok=True)
        c = sqlite3.connect(store.db_path, timeout=10)
        try:
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            c.execute("BEGIN IMMEDIATE")
            existing = dict(c.execute("SELECT key,value FROM meta"))
            expected = {"schema_version": "1", "scope": scope, "project_id": project_id or ""}
            if existing:
                if any(existing.get(k) != v for k, v in expected.items()):
                    raise ArmyError("Store identity/schema mismatch", 5)
            else:
                mode = "bounded-text"
                if fts:
                    try:
                        c.execute("CREATE VIRTUAL TABLE search_fts USING fts5(citation UNINDEXED, content)")
                        mode = "fts5-bm25"
                    except sqlite3.OperationalError:
                        pass
                c.executemany("INSERT INTO meta VALUES(?,?)",
                              list(expected.items()) + [("store_id", str(uuid.uuid4())), ("index_mode", mode)])
            c.commit()
        finally:
            c.close()
        return store

    @contextmanager
    def connect(self, write: bool = False):
        path = contained(self.root, "store.sqlite")
        if not path.is_file():
            raise ArmyError(f"Store is not initialized: {self.root}", 3)
        c = None
        try:
            c = sqlite3.connect(path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=10)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=10000")
            if not write:
                c.execute("PRAGMA query_only=ON")
            meta = dict(c.execute("SELECT key,value FROM meta"))
            if meta.get("schema_version") != "1" or meta.get("scope") != self.scope or meta.get("project_id") != (self.project_id or ""):
                raise ArmyError("Store identity/schema mismatch", 5)
            if write:
                c.execute("BEGIN IMMEDIATE")
            yield c
            if write:
                c.commit()
        except sqlite3.Error as exc:
            if c is not None:
                c.rollback()
            raise ArmyError(f"Store operation failed: {exc}", 5 if "locked" in str(exc) else 2) from exc
        except Exception:
            if c is not None:
                c.rollback()
            raise
        finally:
            if c is not None:
                c.close()

    def _blob(self, text: str) -> str:
        h = sha(text)
        path = contained(self.root, f"blobs/{h}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if sha(path.read_bytes().decode("utf-8")) != h:
                raise ArmyError("Content-addressed blob integrity failure", 5)
            return h
        fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".blob-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
                out.write(text)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return h

    def body(self, content_hash: str) -> str:
        if not re.fullmatch("[0-9a-f]{64}", content_hash):
            raise ArmyError("Invalid body hash")
        text = contained(self.root, f"blobs/{content_hash}.md").read_bytes().decode("utf-8")
        if sha(text) != content_hash:
            raise ArmyError("Blob content does not match recorded hash", 5)
        return text

    def event(self, c, action: str, payload: dict):
        c.execute("INSERT INTO events VALUES(?,?,?,?)",
                  (str(uuid.uuid4()), now(), action, canonical(payload)))

    def _record(self, c, item_id: str, revision: int | None = None) -> dict:
        row = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if row is None:
            raise ArmyError(f"Unknown item in current store: {item_id}", 3)
        if revision is None:
            result = dict(row)
            result["metadata"] = json.loads(result["metadata"])
        else:
            version = c.execute("SELECT record FROM versions WHERE item_id=? AND revision=?", (item_id, revision)).fetchone()
            if version is None:
                raise ArmyError("Unknown item revision", 3)
            result = json.loads(version[0])
        return result

    def get(self, item_id: str, revision: int | None = None, include_inactive: bool = False) -> dict:
        with self.connect() as c:
            current = self._record(c, item_id)
            if not include_inactive and (current["status"] != "active" or
                                        current["expires_at"] and current["expires_at"] <= now()):
                raise ArmyError("Item is inactive or expired", 3)
            item = self._record(c, item_id, revision)
            item["body"] = self.body(item["body_hash"])
            item["scope"] = self.scope
            return item

    @staticmethod
    def validate(kind, title, body, metadata, status, expires_at):
        if kind not in ("knowledge", "memory") or status not in STATUSES:
            raise ArmyError("Invalid item kind or status")
        if not isinstance(title, str) or not title.strip() or len(title) > 500:
            raise ArmyError("Title must contain 1..500 characters")
        if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > MAX_BODY:
            raise ArmyError("Body must be nonempty UTF-8 text, at most 4 MiB")
        if not isinstance(metadata, dict):
            raise ArmyError("Metadata must be an object")
        try:
            serialized = canonical(metadata)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ArmyError("Metadata must be finite JSON data") from exc
        if len(serialized) > 64000:
            raise ArmyError("Metadata exceeds 64k characters")
        if "applies_to" in metadata and (not isinstance(metadata["applies_to"], list) or
                                        any(not isinstance(x, str) for x in metadata["applies_to"])):
            raise ArmyError("applies_to must be an array of project IDs or *")
        for key in ("doi", "arxiv", "url", "memory_key", "evidence_status"):
            if key in metadata and not isinstance(metadata[key], str):
                raise ArmyError(f"{key} must be text")
        return expiry(expires_at)

    def _index(self, c, record: dict, body: str):
        mode = c.execute("SELECT value FROM meta WHERE key='index_mode'").fetchone()[0]
        if mode == "fts5-bm25":
            c.execute("DELETE FROM search_fts WHERE citation IN (SELECT citation FROM chunks WHERE item_id=?)", (record["id"],))
        for start, end, heading, text in chunks(body):
            citation = f'{record["id"]}:v{record["revision"]}:{start}-{end}'
            c.execute("INSERT OR REPLACE INTO chunks VALUES(?,?,?,?,?,?,?)",
                      (citation, record["id"], record["revision"], start, end, heading, text))
            if mode == "fts5-bm25" and record["status"] == "active":
                c.execute("INSERT INTO search_fts VALUES(?,?)", (citation, normalize(record["title"] + " " + text)))

    def _save_version(self, c, record, body):
        c.execute("INSERT INTO versions VALUES(?,?,?)", (record["id"], record["revision"], canonical(record)))
        self._index(c, record, body)
        c.execute("DELETE FROM source_keys WHERE item_id=?", (record["id"],))
        for key in ("doi", "arxiv"):
            if record["metadata"].get(key):
                c.execute("INSERT INTO source_keys VALUES(?,?,?)",
                          (record["id"], key, source_key(record["metadata"][key])))

    def _insert(self, c, kind, title, body, metadata, status="active", expires_at=None, promotion_owned=False) -> tuple[dict, bool]:
        expires_at = self.validate(kind, title, body, metadata, status, expires_at)
        body_hash = self._blob(body)
        fingerprint = sha(canonical([kind, title, body_hash, metadata, expires_at]))
        duplicate = c.execute("SELECT id FROM items WHERE fingerprint=? AND status='active'", (fingerprint,)).fetchone()
        if duplicate and status == "active":
            return self._record(c, duplicate[0]), True
        timestamp = now()
        record = dict(id=str(uuid.uuid4()), kind=kind, revision=1, title=title, status=status,
                      expires_at=expires_at, body_hash=body_hash, fingerprint=fingerprint,
                      metadata=metadata, created_at=timestamp, updated_at=timestamp)
        c.execute("INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  tuple(canonical(record[k]) if k == "metadata" else record[k]
                        for k in ("id", "kind", "revision", "title", "status", "expires_at", "body_hash",
                                  "fingerprint", "metadata", "created_at", "updated_at")))
        self._save_version(c, record, body)
        if self.scope == "global" and not promotion_owned:
            c.execute("INSERT INTO retained_items VALUES(?)", (record["id"],))
        self.event(c, "item.created", {"id": record["id"], "kind": kind})
        return record, False

    def add(self, kind, title, body, metadata=None, expires_at=None) -> dict:
        if self.scope == "global":
            raise ArmyError("Global writes require the approved promotion service", 4)
        with self.connect(True) as c:
            record, duplicate = self._insert(c, kind, title, body, metadata or {}, expires_at=expires_at)
        with self.connect() as c:
            related = c.execute("SELECT DISTINCT s.item_id FROM source_keys s JOIN source_keys own ON s.value=own.value "
                                "JOIN items i ON i.id=s.item_id WHERE own.item_id=? AND s.item_id!=? AND i.status='active'",
                                (record["id"], record["id"])).fetchall()
        return {**record, "scope": self.scope, "duplicate": duplicate, "related_source_items": [r[0] for r in related]}

    def update(self, item_id, expected_revision, *, body=None, title=None, metadata=None, status=None, expires_at=None) -> dict:
        if type(expected_revision) is not int or expected_revision < 1:
            raise ArmyError("expected_revision must be a positive integer")
        if self.scope == "global":
            raise ArmyError("Global mutation requires an approved control action", 4)
        with self.connect(True) as c:
            current = self._record(c, item_id)
            if current["revision"] != expected_revision:
                raise ArmyError("Stale item revision; read current version before editing", 5)
            body = self.body(current["body_hash"]) if body is None else body
            current.update(title=current["title"] if title is None else title,
                           metadata=current["metadata"] if metadata is None else metadata,
                           status=current["status"] if status is None else status,
                           expires_at=current["expires_at"] if expires_at is None else expires_at)
            current["expires_at"] = self.validate(current["kind"], current["title"], body, current["metadata"],
                                                  current["status"], current["expires_at"])
            current.update(body_hash=self._blob(body), revision=expected_revision + 1, updated_at=now())
            current["fingerprint"] = sha(canonical([current["kind"], current["title"], current["body_hash"],
                                                   current["metadata"], current["expires_at"]]))
            c.execute("UPDATE items SET revision=?,title=?,status=?,expires_at=?,body_hash=?,fingerprint=?,metadata=?,updated_at=? WHERE id=?",
                      (current["revision"], current["title"], current["status"], current["expires_at"], current["body_hash"],
                       current["fingerprint"], canonical(current["metadata"]), current["updated_at"], item_id))
            self._save_version(c, current, body)
            self.event(c, "item.updated", {"id": item_id, "revision": current["revision"]})
            return current

    def list(self, kind=None, include_inactive=False, limit=1000):
        if kind not in (None, "knowledge", "memory") or not 1 <= limit <= 10000:
            raise ArmyError("Invalid list kind/limit")
        with self.connect() as c:
            rows = c.execute("SELECT id FROM items WHERE (? IS NULL OR kind=?) AND "
                             "(? OR (status='active' AND (expires_at IS NULL OR expires_at>?))) "
                             "ORDER BY created_at,id LIMIT ?", (kind, kind, include_inactive, now(), limit + 1)).fetchall()
            return {"items": [self._record(c, r[0]) for r in rows[:limit]], "truncated": len(rows) > limit}

    def rebuild(self) -> dict:
        with self.connect(True) as c:
            mode = c.execute("SELECT value FROM meta WHERE key='index_mode'").fetchone()[0]
            if mode == "fts5-bm25":
                c.execute("DELETE FROM search_fts")
            rows = c.execute("SELECT id FROM items").fetchall()
            for row in rows:
                item = self._record(c, row[0])
                self._index(c, item, self.body(item["body_hash"]))
            return {"items": len(rows), "ranking_method": mode, "chunker_version": 1}

    def search(self, query: str, kind=None, limit=20, project_id=None) -> dict:
        if not query.strip() or len(query) > 2000 or kind not in (None, "knowledge", "memory") or not 1 <= limit <= 100:
            raise ArmyError("Invalid search query/kind/limit")
        terms = normalize(query).split()
        with self.connect() as c:
            mode = c.execute("SELECT value FROM meta WHERE key='index_mode'").fetchone()[0]
            where = "i.status='active' AND (i.expires_at IS NULL OR i.expires_at>?) AND (? IS NULL OR i.kind=?) AND ch.revision=i.revision"
            params = [now(), kind, kind]
            fields = "ch.*,i.kind,i.title,i.metadata,i.body_hash"
            exact_ids = {r[0] for r in c.execute("SELECT id FROM items WHERE id=? UNION SELECT item_id FROM source_keys WHERE value=? LIMIT 2001",
                                                 (query, source_key(query)))}
            rows = []
            if exact_ids:
                placeholders = ",".join("?" for _ in exact_ids)
                rows = c.execute(f"SELECT {fields},0 AS rank FROM chunks ch JOIN items i ON i.id=ch.item_id WHERE {where} AND i.id IN ({placeholders}) LIMIT 2001",
                                 (*params, *sorted(exact_ids))).fetchall()
            elif mode == "fts5-bm25" and terms:
                expression = " OR ".join('"' + word + '"' for word in dict.fromkeys(terms))
                rows = c.execute(f"SELECT {fields},bm25(search_fts) AS rank FROM search_fts JOIN chunks ch ON ch.citation=search_fts.citation "
                                 f"JOIN items i ON i.id=ch.item_id WHERE search_fts MATCH ? AND {where} ORDER BY rank,ch.citation LIMIT 2001",
                                 (expression, *params)).fetchall()
            elif terms:
                rows = c.execute(f"SELECT {fields},0 AS rank FROM chunks ch JOIN items i ON i.id=ch.item_id WHERE {where} ORDER BY ch.citation LIMIT 2001",
                                 params).fetchall()
            truncated = len(rows) > 2000
            result = []
            for row in rows[:2000]:
                item = dict(row)
                metadata = json.loads(item.pop("metadata"))
                if item["kind"] == "memory":
                    applicable = metadata.get("applies_to", ["*"])
                    if "*" not in applicable and project_id not in applicable:
                        continue
                if mode == "bounded-text" and not exact_ids and not set(terms).intersection(normalize(item["title"] + " " + item["text"]).split()):
                    continue
                item.update(scope=self.scope, metadata=metadata, ranking_method="exact" if exact_ids else mode,
                            evidence_status=metadata.get("evidence_status", "unverified"), chunker_version=1)
                result.append(item)
            return {"hits": result[:limit], "ranking_method": "exact" if exact_ids else mode,
                    "degraded": mode != "fts5-bm25", "truncated": truncated or len(result) > limit}
