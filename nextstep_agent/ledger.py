"""Append-only action ledger with idempotency and context-freshness checks.

Why append-only? Because Scenario 7 exists. If we ever silently overwrite an
executed action, we lose the ability to say "we did X on your behalf and here's
what happened." That's the exact recovery-mode information the user needs.

Idempotency:
    action_id = sha256(situation_id | step | tool | canonical(args))
Same action, retried after a network drop, resolves to the SAME row. We store
attempt_ids separately so we can still see the retries in the trace.

Context freshness:
    Before executing a previously-confirmed action, we recompute the context
    hash. If it differs, execution PAUSES and the user re-confirms. This
    directly handles: "user approved a message 10 minutes ago, teammate has
    replied since."
"""
from __future__ import annotations
import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from .schema import ExecutedAction, PlannedAction


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def action_id_for(situation_id: str, step: int, tool: str, args: dict) -> str:
    payload = f"{situation_id}|{step}|{tool}|{_canonical(args)}"
    return "act_" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def context_hash(context: dict) -> str:
    return "ctx_" + hashlib.sha256(_canonical(context).encode()).hexdigest()[:16]


class Ledger:
    """File-backed append-only JSONL ledger.

    Thread-safe with a lock (fine for one process; a production version would
    use SELECT ... FOR UPDATE in Postgres. See README for the SQL sketch.)
    """
    def __init__(self, path: str | Path = "./data/ledger.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()

    # --- reads
    def all(self) -> list[dict]:
        with self.path.open() as f:
            return [json.loads(l) for l in f if l.strip()]

    def by_action(self, action_id: str) -> list[dict]:
        return [r for r in self.all() if r.get("action_id") == action_id]

    def find_executed(self, action_id: str) -> ExecutedAction | None:
        for r in reversed(self.all()):
            if r.get("action_id") == action_id and r.get("kind") == "executed" and r.get("ok"):
                return ExecutedAction(**r["executed"])
        return None

    def find_confirmed(self, action_id: str) -> dict | None:
        for r in reversed(self.all()):
            if r.get("action_id") == action_id and r.get("kind") == "confirmed":
                return r
        return None

    # --- writes
    def _append(self, row: dict) -> None:
        row.setdefault("at", datetime.now(timezone.utc).isoformat())
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def propose(self, planned: PlannedAction, context_h: str) -> None:
        self._append({
            "kind": "proposed", "action_id": planned.action_id,
            "tool": planned.tool, "args": planned.args,
            "reversibility": planned.reversibility.value if hasattr(planned.reversibility, "value") else planned.reversibility,
            "context_hash": context_h,
            "preview": planned.preview,
        })

    def confirm(self, action_id: str, context_h: str) -> None:
        self._append({
            "kind": "confirmed", "action_id": action_id,
            "context_hash": context_h,
        })

    def execute(self, executed: ExecutedAction) -> None:
        self._append({
            "kind": "executed", "action_id": executed.action_id,
            "attempt_id": executed.attempt_id,
            "ok": executed.ok, "executed": executed.model_dump(mode="json"),
        })

    def block(self, action_id: str, reason: str) -> None:
        self._append({"kind": "blocked", "action_id": action_id, "reason": reason})

    # --- GDPR-style purge (blocker: "delete everything about me")
    def purge_user(self, situation_ids: Iterable[str]) -> int:
        """Rewrite the ledger without rows whose action_id belongs to `situation_ids`.

        Append-only + purge is a real tension. We solve it with a marker row
        `purged_at` written first, then a compaction pass. Downstream systems
        that replicate from us honor the purge marker.
        """
        # For the challenge scope: simple rewrite. Production would be a
        # tombstone + delayed compaction. Documented in README.
        keep: list[dict] = []
        situation_set = set(situation_ids)
        count = 0
        for r in self.all():
            if any(sid in _canonical(r) for sid in situation_set):
                count += 1
                continue
            keep.append(r)
        with self._lock, self.path.open("w", encoding="utf-8") as f:
            for r in keep:
                f.write(json.dumps(r) + "\n")
        return count


def new_attempt_id() -> str:
    return "att_" + uuid.uuid4().hex[:16]
