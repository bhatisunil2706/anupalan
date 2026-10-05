import uuid
from dataclasses import dataclass
from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, get_db
from app.models import Membership, Organization, User
from app.security import decode_access_token

DB = Annotated[Session, Depends(get_db)]


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(get_settings().cookie_name)


def get_token_payload(request: Request) -> dict:
    token = _token_from_request(request)
    payload = decode_access_token(token) if token else None
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return payload


def get_current_user(db: DB, payload: Annotated[dict, Depends(get_token_payload)]) -> User:
    user = db.get(User, uuid.UUID(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass
class OrgContext:
    user: User
    org: Organization
    role: str

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    @property
    def can_write(self) -> bool:
        return self.role in ("owner", "admin", "member")

    @property
    def is_admin(self) -> bool:
        return self.role in ("owner", "admin")


def get_org_context(
    db: DB, user: CurrentUser, payload: Annotated[dict, Depends(get_token_payload)]
) -> OrgContext:
    org_id = payload.get("org")
    if not org_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "No organisation selected")
    membership = db.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.org_id == uuid.UUID(org_id))
    )
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organisation")
    return OrgContext(user=user, org=membership.organization, role=membership.role)


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

M = TypeVar("M", bound=Base)


def get_owned(db: Session, model: type[M], obj_id: uuid.UUID, ctx: OrgContext) -> M:
    """Fetch a tenant-owned row, 404 if it belongs to another organisation."""
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "org_id", None) != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def ensure_member(db: Session, ctx: OrgContext, user_id: uuid.UUID | None) -> None:
    """Validate that an assigned user belongs to the current organisation."""
    if user_id is None:
        return
    exists = db.scalar(select(Membership.id).where(Membership.user_id == user_id, Membership.org_id == ctx.org_id))
    if not exists:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assigned user is not a member of this organisation")
