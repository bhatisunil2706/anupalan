"""Database engine and sessions with PostgreSQL row-level security (RLS) context.

Every tenant table has an RLS policy that only exposes rows whose org_id matches the transaction-local setting
`app.org_id`. The application connects with a restricted role, so even a query that forgets an org filter can't
read or write another organisation's data. Code paths that legitimately work across organisations (the worker,
public pages that look up an organisation, sign-in) must opt in explicitly with `rls_bypass`.
"""
import uuid
from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_SET_CONTEXT = text(
    "SELECT set_config('app.org_id', :org, true), set_config('app.user_id', :user, true), "
    "set_config('app.rls_bypass', :bypass, true)"
)


def _context_params(info: dict) -> dict:
    return {
        "org": str(info.get("org_id") or ""),
        "user": str(info.get("user_id") or ""),
        "bypass": "on" if info.get("rls_bypass") else "off",
    }


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, transaction, connection) -> None:
    connection.execute(_SET_CONTEXT, _context_params(session.info))


def set_tenant(db: Session, *, org_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None,
               rls_bypass: bool | None = None) -> None:
    """Update the RLS context for this session, including the transaction that is already open."""
    if org_id is not None:
        db.info["org_id"] = org_id
    if user_id is not None:
        db.info["user_id"] = user_id
    if rls_bypass is not None:
        db.info["rls_bypass"] = rls_bypass
    if db.in_transaction():
        db.connection().execute(_SET_CONTEXT, _context_params(db.info))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def system_session() -> Session:
    """Session for trusted background work across all organisations (worker, CLI, seed)."""
    return SessionLocal(info={"rls_bypass": True})
