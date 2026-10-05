import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, get_db, set_tenant
from app.models import ApiKey, Membership, Organization, User, UserSession
from app.security import hash_token
from app.services import sessions

DB = Annotated[Session, Depends(get_db)]

MFA_SETUP_REQUIRED = "MFA_SETUP_REQUIRED"


def _unauthenticated() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")


def get_session(request: Request, db: DB) -> UserSession:
    sess = sessions.lookup(db, sessions.token_from_request(request))
    if sess is None or sess.stage != "full":
        raise _unauthenticated()
    return sess


CurrentSession = Annotated[UserSession, Depends(get_session)]


def get_mfa_pending_session(request: Request, db: DB) -> UserSession:
    sess = sessions.lookup(db, sessions.token_from_request(request))
    if sess is None or sess.stage != "mfa":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your sign-in expired. Please sign in again.")
    return sess


def get_current_user(db: DB, sess: CurrentSession) -> User:
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise _unauthenticated()
    set_tenant(db, user_id=user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass
class OrgContext:
    user: User
    org: Organization
    role: str
    session: UserSession | None = field(default=None, repr=False)

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    @property
    def can_write(self) -> bool:
        return self.role in ("owner", "admin", "member")

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


def active_membership(db: Session, user_id: uuid.UUID, org_id: uuid.UUID) -> Membership | None:
    m = db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.org_id == org_id))
    if m and m.expires_at and m.expires_at <= datetime.now(timezone.utc):
        return None
    return m


def mfa_satisfied(org: Organization, user: User, sess: UserSession) -> bool:
    if not org.require_mfa:
        return True
    return sess.auth_method == "sso" or (user.mfa_enabled and sess.mfa_verified)


def get_org_context(db: DB, user: CurrentUser, sess: CurrentSession) -> OrgContext:
    if not sess.org_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No organisation selected")
    set_tenant(db, org_id=sess.org_id)
    membership = active_membership(db, user.id, sess.org_id)
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this organisation")
    org = membership.organization
    if not mfa_satisfied(org, user, sess):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"{MFA_SETUP_REQUIRED}: {org.name} requires multi-factor authentication. "
                            "Set it up in Account security.")
    return OrgContext(user=user, org=org, role=membership.role, session=sess)


Ctx = Annotated[OrgContext, Depends(get_org_context)]


def require_writer(ctx: Ctx) -> OrgContext:
    if not ctx.can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read-only access")
    return ctx


def require_admin(ctx: Ctx) -> OrgContext:
    if not ctx.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return ctx


WriterCtx = Annotated[OrgContext, Depends(require_writer)]
AdminCtx = Annotated[OrgContext, Depends(require_admin)]


# ---------------------------------------------------------------- API keys (machine access)


@dataclass
class ApiKeyContext:
    key: ApiKey
    org: Organization

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id


def api_key_auth(scope: str):
    """Dependency factory: authenticate `Authorization: Bearer anp_...` and require a scope."""

    def dep(request: Request, db: DB) -> ApiKeyContext:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key required",
                                headers={"WWW-Authenticate": "Bearer"})
        token = auth[7:].strip()
        set_tenant(db, rls_bypass=True)  # the key itself identifies the organisation
        key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_token(token)))
        now = datetime.now(timezone.utc)
        if not key or key.revoked_at or (key.expires_at and key.expires_at <= now):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired API key",
                                headers={"WWW-Authenticate": "Bearer"})
        if scope not in (key.scopes or []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"This API key doesn't have the '{scope}' scope")
        org = db.get(Organization, key.org_id)
        set_tenant(db, org_id=org.id, rls_bypass=False)
        if key.last_used_at is None or (now - key.last_used_at).total_seconds() > 60:
            key.last_used_at = now
        return ApiKeyContext(key=key, org=org)

    return dep


M = TypeVar("M", bound=Base)


def get_owned(db: Session, model: type[M], obj_id: uuid.UUID, ctx) -> M:
    """Fetch a tenant-owned row, 404 if it belongs to another organisation (RLS also hides it)."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "org_id", None) != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def ensure_member(db: Session, ctx: OrgContext, user_id: uuid.UUID | None) -> None:
    """Validate that an assigned user belongs to the current organisation."""
    if user_id is None:
        return
    if not active_membership(db, user_id, ctx.org_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assigned user is not a member of this organisation")
