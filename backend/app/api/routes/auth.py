import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, CurrentUser, get_token_payload
from app.models import Invitation, Membership, Organization, Policy, User
from app.schemas import AcceptInviteIn, LoginIn, MembershipOut, MeOut, SignupIn, SwitchOrgIn, UserBrief
from app.security import create_access_token, hash_password, hash_token, verify_password
from app.services import audit, notify

router = APIRouter(prefix="/auth", tags=["auth"])

# Simple in-process brute-force protection. Use Redis for multi-instance deployments.
_FAILED: dict[str, deque] = defaultdict(deque)
MAX_FAILURES, WINDOW_SECONDS = 5, 15 * 60


def _too_many(key: str) -> bool:
    q = _FAILED[key]
    now = time.monotonic()
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()
    return len(q) >= MAX_FAILURES


def _set_session(response: Response, user_id: uuid.UUID, org_id: uuid.UUID | None) -> None:
    s = get_settings()
    response.set_cookie(
        s.cookie_name,
        create_access_token(user_id, org_id),
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        max_age=s.access_token_minutes * 60,
        path="/",
    )


def _me(db, user: User, org_id: uuid.UUID | None) -> MeOut:
    memberships = db.scalars(select(Membership).where(Membership.user_id == user.id)).all()
    current = next((m for m in memberships if m.org_id == org_id), None)
    return MeOut(
        user=UserBrief.model_validate(user),
        org_id=current.org_id if current else None,
        role=current.role if current else None,
        memberships=[MembershipOut(org_id=m.org_id, org_name=m.organization.name, role=m.role) for m in memberships],
        onboarded=bool(current and current.organization.onboarded_at),
    )


@router.post("/signup", response_model=MeOut, status_code=201)
def signup(body: SignupIn, response: Response, db: DB):
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, full_name=body.full_name.strip(), password_hash=hash_password(body.password))
    org = Organization(name=body.org_name.strip())
    db.add_all([user, org])
    db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
    db.flush()
    audit.record(db, None, "org.created", org, by=user.email)
    db.commit()
    _set_session(response, user.id, org.id)
    return _me(db, user, org.id)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: DB):
    email = body.email.lower()
    key = f"{email}|{request.client.host if request.client else ''}"
    if _too_many(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in 15 minutes.")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        _FAILED[key].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    _FAILED.pop(key, None)
    user.last_login_at = datetime.now(timezone.utc)
    first = db.scalar(select(Membership).where(Membership.user_id == user.id).order_by(Membership.created_at))
    db.commit()
    _set_session(response, user.id, first.org_id if first else None)
    return _me(db, user, first.org_id if first else None)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(get_settings().cookie_name, path="/")


@router.get("/me", response_model=MeOut)
def me(request: Request, db: DB, user: CurrentUser):
    payload = get_token_payload(request)
    org_id = uuid.UUID(payload["org"]) if payload.get("org") else None
    return _me(db, user, org_id)


@router.post("/switch-org", response_model=MeOut)
def switch_org(body: SwitchOrgIn, response: Response, db: DB, user: CurrentUser):
    if not db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == body.org_id)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organisation")
    _set_session(response, user.id, body.org_id)
    return _me(db, user, body.org_id)


def _valid_invitation(db, token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    if not inv or inv.accepted_at or inv.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invitation is invalid or has expired")
    return inv


@router.get("/invitations/{token}")
def invitation_info(token: str, db: DB):
    inv = _valid_invitation(db, token)
    org = db.get(Organization, inv.org_id)
    existing = db.scalar(select(User.id).where(func.lower(User.email) == inv.email.lower()))
    return {"email": inv.email, "org_name": org.name, "role": inv.role, "has_account": bool(existing)}


@router.post("/invitations/accept", response_model=MeOut)
def accept_invitation(body: AcceptInviteIn, request: Request, response: Response, db: DB):
    inv = _valid_invitation(db, body.token)
    user = db.scalar(select(User).where(func.lower(User.email) == inv.email.lower()))
    if user is None:
        if not body.full_name or not body.password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name and password are required to create your account")
        user = User(email=inv.email.lower(), full_name=body.full_name.strip(),
                    password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    else:
        # Existing account: the invitee must be signed in as that user.
        payload = None
        try:
            payload = get_token_payload(request)
        except HTTPException:
            pass
        if not payload or payload.get("sub") != str(user.id):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with the invited email to accept")
    if not db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == inv.org_id)):
        db.add(Membership(user_id=user.id, org_id=inv.org_id, role=inv.role))
        approved = db.scalar(select(func.count()).select_from(Policy).where(
            Policy.org_id == inv.org_id, Policy.status == "approved"))
        if approved:
            notify.queue(db, inv.org_id, key=f"welcome:{user.id}", event="policy_approved", to=[user.email],
                         title=f"Welcome! Please read and acknowledge {approved} company policies",
                         link="/policies")
    inv.accepted_at = datetime.now(timezone.utc)
    db.commit()
    _set_session(response, user.id, inv.org_id)
    return _me(db, user, inv.org_id)
