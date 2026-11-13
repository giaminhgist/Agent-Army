"""Supervised local-console consent, NOT an authenticated host/worker boundary."""
from datetime import datetime, timedelta, timezone
import json
import secrets
import sys
import uuid

from .errors import ArmyError


class ConsoleAuthority:
    """Only a person operating their terminal should invoke this adapter.

    TTY checks reject piping/flags, but cannot distinguish a human from PTY/UI
    automation under the same OS account. Never enable unattended mode from this.
    """
    def __init__(self, action, target_id, request_hash, preview):
        self.expected = (action, target_id, request_hash)
        self.preview = preview
        self.used = False

    def authorize(self, action, target_id, request_hash):
        if self.used or self.expected != (action, target_id, request_hash):
            raise ArmyError("Consent scope changed or already consumed", 4)
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise ArmyError("Supervised approval requires a local interactive terminal; no piped consent", 4)
        # JSON escapes terminal control characters in untrusted preview text.
        print(json.dumps(self.preview, ensure_ascii=True, indent=2), file=sys.stderr)
        challenge = secrets.token_hex(4)
        print(f"SUPERVISED {action}: {target_id}\nHash: {request_hash}\n"
              f"Type {challenge} to authorize this exact action, or Enter to deny: ",
              end="", file=sys.stderr, flush=True)
        try:
            answer = sys.stdin.readline(128).strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise ArmyError("Approval cancelled", 4) from exc
        self.used = True
        if answer != challenge:
            raise ArmyError("Approval denied", 4)
        return {"action": action, "target_id": target_id, "request_hash": request_hash,
                "actor_id": "local-console:supervised-not-authenticated",
                "receipt_id": str(uuid.uuid4()),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
