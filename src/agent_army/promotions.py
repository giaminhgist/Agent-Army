"""Selective global publication with an injected trusted approval authority.

Default CLI publish/revoke fail closed. Explicit console supervision is optional.
Tests use a synthetic authority; hashes alone are NOT proof of user consent.
"""
from __future__ import annotations

import json
import uuid
from typing import Protocol
from urllib.parse import urlsplit

from .errors import ArmyError
from .knowledge import Knowledge
from .store import canonical, expiry, now, sha


class ApprovalAuthority(Protocol):
    def authorize(self, action: str, target_id: str, request_hash: str) -> dict: ...


def receipt(authority, action, target_id, request_hash):
    if authority is None:
        raise ArmyError("Approval authority is not connected; use preview or person-operated console supervision", 4)
    value = authority.authorize(action, target_id, request_hash)
    if not isinstance(value, dict) or value.get("action") != action or value.get("target_id") != target_id or value.get("request_hash") != request_hash:
        raise ArmyError("Approval receipt does not match this action/preview", 4)
    if not isinstance(value.get("actor_id"), str) or not value["actor_id"] or not isinstance(value.get("receipt_id"), str):
        raise ArmyError("Approval provenance is missing", 4)
    expires_at = expiry(value.get("expires_at"))
    if not expires_at or expires_at <= now():
        raise ArmyError("Approval expired", 4)
    # Only persist non-secret audit identifiers, not transport credentials.
    return {k: value[k] for k in ("action", "target_id", "request_hash", "actor_id", "receipt_id", "expires_at")}


class Promotions:
    def __init__(self, knowledge: Knowledge, authority: ApprovalAuthority | None = None):
        self.project = knowledge.store("project")
        self.global_store = knowledge.store("global")
        self.authority = authority

    def prepare(self, item_id: str, *, start=None, end=None, summary=None, title=None, metadata=None):
        if summary is not None and (start is not None or end is not None):
            raise ArmyError("Choose source span OR edited summary")
        with self.project.connect(True) as c:
            item = self.project._record(c, item_id)
            if item["status"] != "active" or item["expires_at"] and item["expires_at"] <= now():
                raise ArmyError("Cannot promote inactive/expired source", 3)
            body = self.project.body(item["body_hash"])
            if (start is None) != (end is None):
                raise ArmyError("Both start and end are required")
            if start is not None:
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(body):
                    raise ArmyError("Invalid source character span")
                target_body = body[start:end]
            else:
                target_body = body if summary is None else summary
            # Never auto-copy project-local paths, source identity, or internal state.
            public = {key: item["metadata"][key] for key in ("doi", "arxiv", "evidence_status", "memory_key")
                      if key in item["metadata"]}
            url = item["metadata"].get("url", "")
            if isinstance(url, str) and urlsplit(url).scheme in ("http", "https"):
                public["url"] = url
            if item["kind"] == "memory":
                public["applies_to"] = ["*"]
            public = public if metadata is None else metadata
            target_title = item["title"] if title is None else title
            self.project.validate(item["kind"], target_title, target_body, public, "active", item["expires_at"])
            target = {"kind": item["kind"], "title": target_title, "body": target_body,
                      "metadata": public, "expires_at": item["expires_at"]}
            snapshot = {"source_id": item_id, "source_revision": item["revision"], "source_hash": item["body_hash"],
                        "source_record_hash": sha(canonical(item)), "span": [start, end],
                        "target": target, "global_store": str(self.global_store.root)}
            fingerprint = sha(canonical(snapshot))
            promotion_id = str(uuid.uuid4())
            c.execute("INSERT INTO promotions VALUES(?,?,?,?,?,?)",
                      (promotion_id, canonical(snapshot), fingerprint, "pending", None, now()))
            self.project.event(c, "promotion.prepared", {"id": promotion_id, "source_id": item_id})
        return self.preview(promotion_id)

    def _proposal(self, c, promotion_id):
        row = c.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
        if row is None:
            raise ArmyError("Unknown promotion in current project", 3)
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot"])
        if sha(canonical(result["snapshot"])) != result["preview_hash"]:
            raise ArmyError("Promotion preview integrity failure", 5)
        if result["snapshot"]["global_store"] != str(self.global_store.root):
            raise ArmyError("Promotion destination changed; prepare a new preview", 5)
        return result

    def preview(self, promotion_id):
        with self.project.connect() as c:
            proposal = self._proposal(c, promotion_id)
            source = self.project._record(c, proposal["snapshot"]["source_id"])
            proposal["source_stale"] = sha(canonical(source)) != proposal["snapshot"]["source_record_hash"]
            proposal["approval_required"] = True
            return proposal

    def apply(self, promotion_id: str, *, after_global_commit=None):
        # Consistent lock order: project, then global. Hold source revision stable through publication.
        with self.project.connect(True) as pc:
            proposal = self._proposal(pc, promotion_id)
            if proposal["state"] == "revoked":
                raise ArmyError("Revoked promotion cannot be republished; prepare a new preview", 5)
            snapshot = proposal["snapshot"]
            source = self.project._record(pc, snapshot["source_id"])
            if sha(canonical(source)) != snapshot["source_record_hash"] or source["status"] != "active" or source["expires_at"] and source["expires_at"] <= now():
                raise ArmyError("Source changed/expired after preview; prepare and approve a new preview", 5)
            self.project.body(source["body_hash"])  # Verify source blob still matches the preview, not just DB metadata.
            approved = receipt(self.authority, "publish", promotion_id, proposal["preview_hash"])
            with self.global_store.connect(True) as gc:
                link = gc.execute("SELECT * FROM promotion_links WHERE id=?", (promotion_id,)).fetchone()
                if link:
                    if link["preview_hash"] != proposal["preview_hash"] or link["revoked"]:
                        raise ArmyError("Global promotion link conflicts with preview", 5)
                    target_id = link["item_id"]
                else:
                    target = snapshot["target"]
                    record, duplicate = self.global_store._insert(gc, target["kind"], target["title"], target["body"],
                                                                  target["metadata"], expires_at=target["expires_at"], promotion_owned=True)
                    target_id = record["id"]
                    gc.execute("INSERT INTO promotion_links VALUES(?,?,?,?,?,?,?)",
                               (promotion_id, proposal["preview_hash"], target_id, record["revision"], record["body_hash"], 0, canonical(approved)))
                    self.global_store.event(gc, "promotion.published", {"promotion_id": promotion_id, "item_id": target_id, "duplicate": duplicate})
            if after_global_commit:
                after_global_commit()  # Test fault injection; not exposed by CLI.
            pc.execute("UPDATE promotions SET state='published',target_id=? WHERE id=?", (target_id, promotion_id))
            self.project.event(pc, "promotion.acknowledged", {"id": promotion_id, "target_id": target_id})
            return {"id": promotion_id, "target_id": target_id, "state": "published"}

    def reconcile(self, promotion_id):
        """Recover project acknowledgement after a committed global transaction; never publish."""
        with self.project.connect(True) as pc:
            proposal = self._proposal(pc, promotion_id)
            with self.global_store.connect() as gc:
                link = gc.execute("SELECT * FROM promotion_links WHERE id=?", (promotion_id,)).fetchone()
            if link is None:
                return {"id": promotion_id, "state": proposal["state"], "global_commit": False}
            if link["preview_hash"] != proposal["preview_hash"]:
                raise ArmyError("Recovery preview hash mismatch", 5)
            state = "revoked" if link["revoked"] else "published"
            pc.execute("UPDATE promotions SET state=?,target_id=? WHERE id=?", (state, link["item_id"], promotion_id))
            self.project.event(pc, "promotion.reconciled", {"id": promotion_id, "state": state})
            return {"id": promotion_id, "state": state, "target_id": link["item_id"], "global_commit": True}

    def revoke(self, promotion_id):
        with self.project.connect(True) as pc:
            proposal = self._proposal(pc, promotion_id)
            approved = receipt(self.authority, "revoke", promotion_id, proposal["preview_hash"])
            with self.global_store.connect(True) as gc:
                link = gc.execute("SELECT * FROM promotion_links WHERE id=?", (promotion_id,)).fetchone()
                if link is None or link["preview_hash"] != proposal["preview_hash"]:
                    raise ArmyError("No matching global promotion to revoke", 5)
                gc.execute("UPDATE promotion_links SET revoked=1 WHERE id=?", (promotion_id,))
                others = gc.execute("SELECT count(*) FROM promotion_links WHERE item_id=? AND revoked=0", (link["item_id"],)).fetchone()[0]
                retained = gc.execute("SELECT 1 FROM retained_items WHERE item_id=?", (link["item_id"],)).fetchone()
                if not others and not retained:
                    record = self.global_store._record(gc, link["item_id"])
                    # Do not erase a later revision that this promotion did not publish.
                    if record["revision"] == link["target_revision"] and record["body_hash"] == link["body_hash"]:
                        record.update(status="revoked", revision=record["revision"] + 1, updated_at=now())
                        gc.execute("UPDATE items SET status=?,revision=?,updated_at=? WHERE id=?",
                                   ("revoked", record["revision"], record["updated_at"], link["item_id"]))
                        self.global_store._save_version(gc, record, self.global_store.body(record["body_hash"]))
                self.global_store.event(gc, "promotion.revoked", {"promotion_id": promotion_id, "receipt": approved})
            pc.execute("UPDATE promotions SET state='revoked' WHERE id=?", (promotion_id,))
            return {"id": promotion_id, "state": "revoked", "other_active_links": others,
                    "note": "Future retrieval excludes revoked-only content; existing model contexts are not erased."}
