"""Recoverable file transactions. Cooperative lock; no same-user security boundary."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from .errors import ArmyError
from .store import canonical


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def safe(path):
    path = Path(path).absolute()
    # Reject symlinks/junctions, including ancestors, not just escaped final paths.
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ArmyError(f"Linked filesystem target is not supported: {part}", 5)
        if os.name == "nt" and part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400:
            raise ArmyError(f"Reparse-point target is not supported: {part}", 5)
    return path


def read(path):
    path = safe(path)
    return path.read_bytes() if path.exists() else None


def write(path, data):
    path = safe(path)
    if data is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".army-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        safe(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def lock(state):
    state = safe(state)
    state.mkdir(parents=True, exist_ok=True)
    path = safe(state / "lock")
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ArmyError("Another Army installer/migration transaction is active", 5) from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def encode(data):
    return base64.b64encode(data).decode("ascii") if data is not None else None


def decode(data):
    return base64.b64decode(data, validate=True) if data is not None else None


def journal(state, transaction):
    try:
        if str(uuid.UUID(transaction)) != transaction:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ArmyError("Invalid transaction ID") from exc
    path = safe(Path(state) / "transactions" / (transaction + ".json"))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ArmyError("Cannot read transaction journal", 5) from exc
    return path, value


def rollback_preview(state, transaction):
    _, value = journal(state, transaction)
    conflicts = []
    for entry in value["entries"]:
        if digest(read(entry["path"])) not in (entry["before_hash"], entry["after_hash"]):
            conflicts.append(entry["path"])
    return {"transaction": transaction, "journal": value, "conflicts": conflicts}


def restore(state, transaction):
    path, value = journal(state, transaction)
    conflicts = rollback_preview(state, transaction)["conflicts"]
    if conflicts:
        raise ArmyError("Rollback would overwrite edited files: " + ", ".join(conflicts), 5)
    for entry in value["entries"]:
        if digest(decode(entry["before"])) != entry["before_hash"] or digest(decode(entry["after"])) != entry["after_hash"]:
            raise ArmyError("Backup integrity mismatch", 5)
    for entry in reversed(value["entries"]):
        before = decode(entry["before"])
        if digest(before) != entry["before_hash"]:
            raise ArmyError("Backup integrity mismatch", 5)
        if digest(read(entry["path"])) != entry["before_hash"]:
            write(entry["path"], before)
    value["state"] = "rolled_back"
    write(path, canonical(value).encode())
    return {"transaction": transaction, "state": "rolled_back"}


def commit(state, entries, approval, *, fault=None):
    """Caller holds lock. Entries: absolute path, exact before/after bytes."""
    state = Path(state)
    pending = state / "transactions"
    if pending.exists():
        for path in pending.glob("*.json"):
            if json.loads(path.read_text(encoding="utf-8"))["state"] == "prepared":
                raise ArmyError("Interrupted transaction needs explicit rollback before another install", 5)
    for entry in entries:
        if read(entry["path"]) != entry["before"]:
            raise ArmyError("Destination changed since preview", 5)
    transaction = str(uuid.uuid4())
    value = {"state": "prepared", "approval": approval, "entries": [
        {"path": str(e["path"]), "before": encode(e["before"]), "after": encode(e["after"]),
         "before_hash": digest(e["before"]), "after_hash": digest(e["after"])} for e in entries]}
    path = safe(state / "transactions" / (transaction + ".json"))
    write(path, canonical(value).encode())
    try:
        for i, entry in enumerate(entries):
            if read(entry["path"]) != entry["before"]:
                raise ArmyError("Concurrent edit detected", 5)
            write(entry["path"], entry["after"])
            if fault:
                fault(i)
        value["state"] = "committed"
        write(path, canonical(value).encode())
    except Exception:
        restore(state, transaction)
        raise
    # BaseException simulates hard process interruption; durable journal remains.
    return {"transaction": transaction, "state": "committed", "changed_files": len(entries)}
