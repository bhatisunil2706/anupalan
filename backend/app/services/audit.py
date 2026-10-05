"""Append-only, hash-chained audit log.

Each organisation has its own chain: entry N stores sha256(prev_hash + canonical JSON of entry N). Changing or
deleting any past entry breaks every hash after it, which `verify_chain` detects. The runtime database role has
no UPDATE or DELETE permission on audit_logs, so the application itself can't rewrite history either.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import set_tenant
from app.models import AuditLog
from app.request_context import client_ip, user_agent

GENESIS = "0" * 64

def _clean(detail: dict) -> dict:
    return {k: (v if isinstance(v, (int, float, bool, type(None), list, dict, str)) else str(v))
            for k, v in detail.items()}


def entry_hash(entry: AuditLog) -> str:
    at = entry.at.astimezone(timezone.utc).isoformat(timespec="microseconds")
    body = json.dumps({
        "seq": entry.seq, "org_id": str(entry.org_id or ""), "user_id": str(entry.user_id or ""),
        "action": entry.action, "entity_type": entry.entity_type, "entity_id": entry.entity_id,
        "detail": entry.detail, "ip": entry.ip, "user_agent": entry.user_agent, "at": at,
    }, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((entry.prev_hash + body).encode()).hexdigest()


def write(db: Session, *, org_id: uuid.UUID | None, user_id: uuid.UUID | None, action: str, entity=None,
          detail: dict | None = None) -> AuditLog:
    key = str(org_id) if org_id else "system"
    if org_id and db.info.get("org_id") != org_id and not db.info.get("rls_bypass"):
        set_tenant(db, org_id=org_id)
    conn = db.connection()
    conn.execute(text("INSERT INTO audit_chain_heads (chain_key, seq, hash) VALUES (:k, 0, :g) "
                      "ON CONFLICT (chain_key) DO NOTHING"), {"k": key, "g": GENESIS})
    seq, prev = conn.execute(text("SELECT seq, hash FROM audit_chain_heads WHERE chain_key = :k FOR UPDATE"),
                             {"k": key}).one()
    entry = AuditLog(
        id=uuid.uuid4(), org_id=org_id, user_id=user_id, action=action,
        entity_type=type(entity).__name__ if entity is not None else "",
        entity_id=str(getattr(entity, "id", "") or "") if entity is not None else "",
        detail=_clean(detail or {}), ip=client_ip.get()[:64], user_agent=user_agent.get()[:300],
        at=datetime.now(timezone.utc),
        seq=seq + 1, prev_hash=prev,
    )
    entry.hash = entry_hash(entry)
    db.add(entry)
    conn.execute(text("UPDATE audit_chain_heads SET seq = :s, hash = :h WHERE chain_key = :k"),
                 {"s": entry.seq, "h": entry.hash, "k": key})
    return entry


def record(db: Session, ctx, action: str, entity=None, **detail) -> None:
    """Append an audit entry for the current organisation context (ctx may be None for system actions)."""
    write(db, org_id=ctx.org_id if ctx else None, user_id=ctx.user.id if ctx else None, action=action,
          entity=entity, detail=detail)


def verify_chain(db: Session, org_id: uuid.UUID) -> dict:
    """Recompute the organisation's chain. Returns {"ok": bool, "entries": n, "broken_at": seq | None}."""
    prev, expected_seq, n = GENESIS, 1, 0
    for e in db.scalars(select(AuditLog).where(AuditLog.org_id == org_id).order_by(AuditLog.seq)):
        n += 1
        if e.seq != expected_seq or e.prev_hash != prev or entry_hash(e) != e.hash:
            return {"ok": False, "entries": n, "broken_at": e.seq or expected_seq}
        prev, expected_seq = e.hash, expected_seq + 1
    head = db.execute(text("SELECT seq, hash FROM audit_chain_heads WHERE chain_key = :k"),
                      {"k": str(org_id)}).first()
    if head and (head.seq != n or head.hash != prev):
        return {"ok": False, "entries": n, "broken_at": n + 1 if head.seq > n else n}
    return {"ok": True, "entries": n, "broken_at": None, "head": prev}
