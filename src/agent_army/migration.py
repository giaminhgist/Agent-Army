"""Read-only legacy discovery, approved import-copy, and non-destructive rollback."""
import json
import os
import posixpath
from pathlib import Path
import re

from .errors import ArmyError
from .paths import contained
from .promotions import receipt
from .store import canonical, now, sha, MAX_BODY
from . import transactions as tx


class Migration:
    def __init__(self, source, source_kind, store):
        self.source = tx.safe(source).resolve()
        if source_kind not in ("project", "global") or not self.source.is_dir():
            raise ArmyError("Migration needs an existing project/global legacy root")
        self.source_kind, self.store = source_kind, store
        tx.safe(store.root)
        # Project may contain its new .agent-army destination, but selected roots never may.
        if self.source == store.root or self.source.is_relative_to(store.root):
            raise ArmyError("Legacy source must not be inside destination store")

    def _files(self, selections):
        roots = ([".research-agent/kb", ".research-agent/memory", "research-wiki",
                  ".research-agent/tasks", ".research-agent/runs", ".research-agent/reviews",
                  ".research-agent/artifacts"] if self.source_kind == "project" else ["knowledge"])
        files, excluded = {}, []
        for relative in roots:
            tx.safe(self.source / relative)
            root = contained(self.source, relative)
            tx.safe(root)
            if not root.exists():
                continue
            for directory, dirs, names in os.walk(root, followlinks=False):
                for name in dirs:
                    tx.safe(Path(directory) / name)
                for name in names:
                    path = tx.safe(Path(directory) / name)
                    rel = path.relative_to(self.source).as_posix()
                    if path.name.startswith(".") or path.suffix in (".sqlite", ".db") or "promotion-queue" in path.name:
                        excluded.append(rel)
                        continue
                    if selections and rel not in selections:
                        continue
                    if path.is_relative_to(self.store.root):
                        raise ArmyError("Selected source overlaps destination")
                    if path.stat().st_size > MAX_BODY:
                        raise ArmyError(f"Source exceeds 4 MiB; select a smaller subset: {rel}")
                    files[rel] = path.read_bytes()
                    if len(files) > 2000 or sum(len(v) for v in files.values()) > 64 * 1024 * 1024:
                        raise ArmyError("Migration exceeds 2000 files / 64 MiB; select a smaller subset")
        if selections and set(selections) - set(files):
            raise ArmyError("Selection missing, excluded or outside supported legacy roots: " + ", ".join(sorted(set(selections) - set(files))))
        return files, excluded

    def _record(self, relative, data):
        memory = relative.startswith(".research-agent/memory/")
        knowledge = relative.startswith((".research-agent/kb/", "knowledge/", "research-wiki/"))
        if not (knowledge or memory) or Path(relative).suffix.lower() not in (".md", ".txt"):
            return None
        try:
            body = data.decode("utf-8-sig")
        except UnicodeError:
            return None
        if not body.strip():
            return None
        metadata = {"evidence_status": "unverified", "legacy_path": relative,
                    "legacy_source_id": sha(str(self.source)), "legacy_bytes_sha256": tx.digest(data),
                    "legacy_key": Path(relative).stem}
        title = Path(relative).stem
        # Only parse scalar fields emitted by the legacy writer; preserve full body/frontmatter.
        if body.startswith("---"):
            parts = body.split("---", 2)
            if len(parts) == 3:
                for line in parts[1].splitlines():
                    key, separator, value = line.partition(":")
                    if separator and key in ("title", "doi", "arxiv", "url", "slug"):
                        value = value.strip()
                        try:
                            value = json.loads(value) if value.startswith('"') else value
                        except ValueError:
                            continue
                        if isinstance(value, str) and value:
                            if key == "title":
                                title = value
                            else:
                                metadata["legacy_key" if key == "slug" else key] = value
        record = {"kind": "memory" if memory else "knowledge", "title": title[:500], "body": body, "metadata": metadata}
        self.store.validate(record["kind"], record["title"], body, metadata, "active", None)
        return record

    def _plan(self, selections=None):
        files, excluded = self._files(selections or [])
        entries = []
        keys, cites, unresolved_links = set(), set(), []
        for relative, data in sorted(files.items()):
            record = self._record(relative, data)
            text = data.decode("utf-8-sig", errors="replace")
            if relative.endswith(".bib"):
                keys.update(re.findall(r"@\w+\s*\{\s*([^,\s]+)\s*,", text))
            if record:
                keys.add(record["metadata"]["legacy_key"])
                cites.update(re.findall(r"\[@([^\]\s;]+)", text))
                for link in re.findall(r"\]\(([^)\s]+)\)", text):
                    target = link.split("#", 1)[0]
                    if target and ":" not in target:
                        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), target))
                        if resolved not in files:
                            unresolved_links.append({"source": relative, "link": link})
            entries.append({"source": relative, "sha256": tx.digest(data), "bytes": len(data),
                            "mode": "import" if record else "archive_only", "record": record})
        with self.store.connect() as c:
            store_id = c.execute("SELECT value FROM meta WHERE key='store_id'").fetchone()[0]
            destination = [tuple(row) for row in c.execute("SELECT id,revision,status,body_hash,fingerprint FROM items ORDER BY id")]
        payload = {"source": str(self.source), "source_kind": self.source_kind,
                   "destination": str(self.store.root), "scope": self.store.scope, "store_id": store_id,
                   "destination_hash": sha(canonical(destination)), "select": sorted(selections or []),
                   "entries": entries, "counts": {"files": len(entries), "import": sum(e["record"] is not None for e in entries)},
                   "excluded_files": sorted(excluded), "excluded_categories": ["approvals", "sessions", "loop/autonomy", "project settings", "skills installers", "derived SQLite indexes", "promotion queue"],
                   "unresolved_citation_keys": sorted(cites - keys), "bib_keys": sorted(keys),
                   "unresolved_relative_links": unresolved_links,
                   "source_modified": False, "resume_jobs": False}
        return {"preview": payload, "request_hash": sha(canonical(payload))}, files

    def plan(self, selections=None):
        return self._plan(selections)[0]

    def _history(self, c):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='army_migrations'").fetchone():
            return []
        return [json.loads(row[0]) for row in c.execute("SELECT record FROM army_migrations")]

    def apply(self, plan, authority=None, *, fault=None):
        migration_id = plan["request_hash"]
        # A completed request is idempotent even though destination_hash changed.
        with self.store.connect() as c:
            for previous in self._history(c):
                if previous["id"] == migration_id:
                    if previous["state"] == "rolled_back":
                        raise ArmyError("Migration was rolled back; prepare a new preview", 5)
                    return dict(previous, replay=True)
        fresh, files = self._plan(plan["preview"]["select"])
        if fresh != plan:
            raise ArmyError("Migration preview/source/destination changed", 5)
        if not files:
            raise ArmyError("No supported legacy data selected", 3)
        approved = receipt(authority, "migrate", str(self.store.root), migration_id)
        with self.store.connect(True) as c:
            fresh, files = self._plan(plan["preview"]["select"])
            if fresh != plan:
                raise ArmyError("Migration changed during approval", 5)
            c.execute("CREATE TABLE IF NOT EXISTS army_migrations(id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            mapping = []
            for index, entry in enumerate(plan["preview"]["entries"]):
                # Exact-byte snapshot keeps relative links; never overwrite an existing different backup.
                path = tx.safe(contained(self.store.root, "migrations/" + migration_id + "/snapshot/" + entry["source"]))
                data = files[entry["source"]]
                existing = tx.read(path)
                if existing is not None and existing != data:
                    raise ArmyError("Migration snapshot conflict", 5)
                if existing is None:
                    tx.write(path, data)
                if tx.digest(tx.read(path)) != entry["sha256"]:
                    raise ArmyError("Snapshot verification failed", 5)
                record = entry["record"]
                target = {"source": entry["source"], "source_hash": entry["sha256"], "snapshot": str(path.relative_to(self.store.root)), "item_id": None}
                if record:
                    item, duplicate = self.store._insert(c, **record)
                    target.update(item_id=item["id"], revision=item["revision"], body_hash=item["body_hash"], created=not duplicate)
                mapping.append(target)
                if fault:
                    fault(index)
            if self._files(plan["preview"]["select"])[0] != files:
                raise ArmyError("Legacy source changed during import", 5)
            result = {"id": migration_id, "state": "imported", "approval": approved,
                      "mapping": mapping, "counts": plan["preview"]["counts"], "imported_at": now()}
            c.execute("INSERT INTO army_migrations VALUES(?,?)", (migration_id, canonical(result)))
            self.store.event(c, "migration.imported", {"id": migration_id, "files": len(mapping)})
        return result

    def rollback_plan(self, migration_id):
        with self.store.connect() as c:
            history = self._history(c)
            record = next((r for r in history if r["id"] == migration_id), None)
            if record is None or record["state"] != "imported":
                raise ArmyError("No active migration with this ID", 3)
            changes, preserved, conflicts = [], [], []
            for entry in record["mapping"]:
                item_id = entry["item_id"]
                if not item_id:
                    continue
                links = [e for r in history for e in r["mapping"] if e["item_id"] == item_id]
                active_others = any(r["state"] == "imported" and r["id"] != migration_id and any(e["item_id"] == item_id for e in r["mapping"]) for r in history)
                if active_others or not any(e.get("created") for e in links):
                    preserved.append(item_id)
                    continue
                item = self.store._record(c, item_id)
                if item["revision"] != entry["revision"] or item["body_hash"] != entry["body_hash"]:
                    conflicts.append(item_id)
                else:
                    changes.append(item_id)
            payload = {"id": migration_id, "destination": str(self.store.root), "record": record,
                       "revoke": sorted(set(changes)), "preserve": sorted(set(preserved)), "conflicts": sorted(set(conflicts)),
                       "snapshots_kept": True, "global_promotions_not_revoked": True}
        return {"preview": payload, "request_hash": sha(canonical(payload))}

    def rollback(self, plan, authority=None):
        migration_id = plan["preview"]["id"]
        if self.rollback_plan(migration_id) != plan or plan["preview"]["conflicts"]:
            raise ArmyError("Migration rollback stale or imported item edited", 5)
        approved = receipt(authority, "migration-rollback", migration_id, plan["request_hash"])
        with self.store.connect(True) as c:
            if self.rollback_plan(migration_id) != plan:
                raise ArmyError("Migration changed during rollback approval", 5)
            for item_id in plan["preview"]["revoke"]:
                item = self.store._record(c, item_id)
                item.update(status="revoked", revision=item["revision"] + 1, updated_at=now())
                c.execute("UPDATE items SET status=?,revision=?,updated_at=? WHERE id=?", (item["status"], item["revision"], item["updated_at"], item_id))
                self.store._save_version(c, item, self.store.body(item["body_hash"]))
            record = plan["preview"]["record"]
            record.update(state="rolled_back", rollback_approval=approved)
            c.execute("UPDATE army_migrations SET record=? WHERE id=?", (canonical(record), migration_id))
            self.store.event(c, "migration.rolled_back", {"id": migration_id})
        return {"id": migration_id, "state": "rolled_back", "snapshots_kept": True}
