"""Server-side sessions: create, look up, refresh, revoke; cookie handling."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Organization, UserSession
from app.request_context import client_ip, user_agent
from app.security import hash_token

TOUCH_EVERY = timedelta(seconds=60)
DEFAULT_IDLE_MINUTES = 120


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_session(db: Session, response: Response, *, user_id: uuid.UUID, org_id: uuid.UUID | None,
                   stage: str = "full", auth_method: str = "password", mfa_verified: bool = False) -> UserSession:
    s = get_settings()
    token = secrets.token_urlsafe(32)
    lifetime = timedelta(minutes=s.mfa_challenge_minutes) if stage == "mfa" else timedelta(
        hours=s.session_absolute_hours)
    sess = UserSession(user_id=user_id, token_hash=hash_token(token), org_id=org_id, stage=stage,
                       auth_method=auth_method, mfa_verified=mfa_verified, ip=client_ip.get()[:64],
                       user_agent=user_agent.get()[:300], expires_at=_now() + lifetime)
    db.add(sess)
    db.flush()
    set_cookies(response, token, int(lifetime.total_seconds()))
    return sess


def set_cookies(response: Response, token: str, max_age: int) -> None:
    s = get_settings()
    response.set_cookie(s.cookie_name, token, httponly=True, secure=s.cookie_secure, samesite="lax",
                        max_age=max_age, path="/")
    # Double-submit CSRF token: readable by our JS, sent back in X-CSRF-Token on every state-changing request.
    response.set_cookie(s.csrf_cookie_name, secrets.token_urlsafe(24), httponly=False, secure=s.cookie_secure,
                        samesite="strict", max_age=max_age, path="/")


def clear_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.cookie_name, path="/", secure=s.cookie_secure, httponly=True, samesite="lax")
    response.delete_cookie(s.csrf_cookie_name, path="/", secure=s.cookie_secure, samesite="strict")


def token_from_request(request: Request) -> str | None:
    return request.cookies.get(get_settings().cookie_name)


def lookup(db: Session, token: str | None) -> UserSession | None:
    """Return a live session for the token, enforcing absolute expiry and the organisation's idle timeout."""
    if not token:
        return None
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    now = _now()
    if sess is None or sess.revoked_at is not None or sess.expires_at <= now:
        return None
    idle = DEFAULT_IDLE_MINUTES
    from app.db import set_tenant

    set_tenant(db, user_id=sess.user_id, org_id=sess.org_id)  # server-side values, safe to scope by
    if sess.org_id:
        idle = db.scalar(select(Organization.session_idle_minutes).where(Organization.id == sess.org_id)) or idle
    if sess.stage == "full" and now - sess.last_seen_at > timedelta(minutes=idle):
        sess.revoked_at = now
        db.commit()
        return None
    if now - sess.last_seen_at > TOUCH_EVERY:
        sess.last_seen_at = now
        db.commit()
    return sess


def revoke(db: Session, sess: UserSession) -> None:
    sess.revoked_at = _now()


def revoke_all(db: Session, user_id: uuid.UUID, except_id: uuid.UUID | None = None) -> int:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id is not None:
        q = q.where(UserSession.id != except_id)
    return db.execute(q.values(revoked_at=_now())).rowcount


def active_sessions(db: Session, user_id: uuid.UUID) -> list[UserSession]:
    now = _now()
    return list(db.scalars(select(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > now,
        UserSession.stage == "full").order_by(UserSession.last_seen_at.desc())))


def seen_before(db: Session, user_id: uuid.UUID, ip: str, ua: str, days: int = 60) -> bool:
    since = _now() - timedelta(days=days)
    return db.scalar(select(UserSession.id).where(
        UserSession.user_id == user_id, UserSession.created_at > since, UserSession.stage == "full",
        UserSession.ip == ip, UserSession.user_agent == ua).limit(1)) is not None
