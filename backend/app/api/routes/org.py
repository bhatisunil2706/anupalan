import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, AdminCtx, Ctx
from app.models import AuditLog, Framework, Invitation, Membership, OrgFramework, User
from app.schemas import InviteIn, MemberOut, OnboardingIn, OrgOut, OrgUpdate, RoleIn, UserBrief
from app.security import new_token
from app.services import audit, notify
from app.services.compliance import PROFILE_FLAGS, provision_controls
from app.services.policies import create_policy_from_template

router = APIRouter(prefix="/org", tags=["organisation"])


@router.get("", response_model=OrgOut)
def get_org(ctx: Ctx):
    return ctx.org


@router.get("/profile-flags")
def profile_flags():
    return [{"key": k, "label": v} for k, v in PROFILE_FLAGS.items()]


@router.patch("", response_model=OrgOut)
def update_org(body: OrgUpdate, db: DB, ctx: AdminCtx):
    org = ctx.org
    data = body.model_dump(exclude_unset=True)
    if "profile" in data:
        unknown = set(data["profile"]) - set(PROFILE_FLAGS)
        if unknown:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown profile flags: {sorted(unknown)}")
        data["profile"] = {**(org.profile or {}), **data["profile"]}
    for k, v in data.items():
        setattr(org, k, v)
    created = provision_controls(db, org)
    audit.record(db, ctx, "org.updated", org, fields=list(data), controls_created=created)
    db.commit()
    return org


@router.post("/onboarding", response_model=OrgOut)
def onboarding(body: OnboardingIn, db: DB, ctx: AdminCtx):
    org = ctx.org
    unknown = set(body.profile) - set(PROFILE_FLAGS)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown profile flags: {sorted(unknown)}")
    frameworks = db.scalars(select(Framework).where(Framework.code.in_(body.framework_codes))).all()
    if len(frameworks) != len(set(body.framework_codes)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown framework code")
    org.sector, org.employee_count = body.sector, body.employee_count
    org.profile = {**(org.profile or {}), **body.profile}
    enabled = set(db.scalars(select(OrgFramework.framework_id).where(OrgFramework.org_id == org.id)))
    for fw in frameworks:
        if fw.id not in enabled:
            db.add(OrgFramework(org_id=org.id, framework_id=fw.id))
    db.flush()
    created = provision_controls(db, org)
    policies = 0
    if body.create_policies:
        from app.models import PolicyTemplate

        for tpl in db.scalars(select(PolicyTemplate)):
            if create_policy_from_template(db, ctx, tpl, skip_existing=True):
                policies += 1
    from app.api.routes.training import ensure_assignments

    ensure_assignments(db, org.id)
    org.onboarded_at = org.onboarded_at or datetime.now(timezone.utc)
    audit.record(db, ctx, "org.onboarded", org, frameworks=body.framework_codes, controls=created, policies=policies)
    db.commit()
    return org


# ---------------------------------------------------------------- members


@router.get("/members", response_model=list[MemberOut])
def members(db: DB, ctx: Ctx):
    rows = db.scalars(select(Membership).where(Membership.org_id == ctx.org_id).order_by(Membership.created_at))
    return [MemberOut(user=UserBrief.model_validate(m.user), role=m.role, joined_at=m.created_at) for m in rows]


def _membership(db, ctx, user_id: uuid.UUID) -> Membership:
    m = db.scalar(select(Membership).where(Membership.org_id == ctx.org_id, Membership.user_id == user_id))
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return m


def _owner_count(db, ctx) -> int:
    return db.scalar(
        select(func.count()).select_from(Membership).where(Membership.org_id == ctx.org_id, Membership.role == "owner")
    )


@router.patch("/members/{user_id}", response_model=MemberOut)
def change_role(user_id: uuid.UUID, body: RoleIn, db: DB, ctx: AdminCtx):
    m = _membership(db, ctx, user_id)
    if (m.role == "owner" or body.role == "owner") and ctx.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can grant or remove the owner role")
    if m.role == "owner" and body.role != "owner" and _owner_count(db, ctx) <= 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "An organisation needs at least one owner")
    old = m.role
    m.role = body.role
    audit.record(db, ctx, "member.role_changed", m.user, old=old, new=body.role)
    db.commit()
    return MemberOut(user=UserBrief.model_validate(m.user), role=m.role, joined_at=m.created_at)


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, db: DB, ctx: AdminCtx):
    m = _membership(db, ctx, user_id)
    if m.role == "owner" and (ctx.role != "owner" or _owner_count(db, ctx) <= 1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot remove this owner")
    audit.record(db, ctx, "member.removed", m.user)
    db.delete(m)
    db.commit()


# ---------------------------------------------------------------- invitations


@router.get("/invitations")
def list_invitations(db: DB, ctx: AdminCtx):
    now = datetime.now(timezone.utc)
    rows = db.scalars(
        select(Invitation).where(Invitation.org_id == ctx.org_id, Invitation.accepted_at.is_(None),
                                 Invitation.expires_at > now).order_by(Invitation.created_at.desc())
    )
    return [{"id": i.id, "email": i.email, "role": i.role, "expires_at": i.expires_at} for i in rows]


@router.post("/invitations", status_code=201)
def invite(body: InviteIn, db: DB, ctx: AdminCtx):
    if body.role == "owner" and ctx.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can invite owners")
    if not ctx.user.email_verified_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Confirm your own email address before inviting others")
    if body.role == "auditor" and not body.access_days:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set how many days the auditor should have access")
    email = body.email.lower()
    existing_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if existing_user and db.scalar(
        select(Membership).where(Membership.org_id == ctx.org_id, Membership.user_id == existing_user.id)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "This person is already a member")
    token, token_hash = new_token()
    access_until = (datetime.now(timezone.utc) + timedelta(days=body.access_days)) if body.access_days else None
    inv = Invitation(org_id=ctx.org_id, email=email, role=body.role, token_hash=token_hash,
                     invited_by_id=ctx.user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                     access_expires_at=access_until)
    db.add(inv)
    audit.record(db, ctx, "member.invited", inv, email=email, role=body.role)
    db.commit()
    url = f"{get_settings().public_url.rstrip('/')}/invite/{token}"
    emailed = True
    try:
        notify.send_email([email], f"{ctx.user.full_name} invited you to {ctx.org.name}",
                          f"You've been invited to join {ctx.org.name}'s compliance workspace as {body.role}.\n\n"
                          f"Accept the invitation (valid for 7 days):\n{url}")
    except Exception:  # noqa: BLE001 - the admin can still copy the link
        emailed = False
    return {"id": inv.id, "email": email, "role": body.role, "invite_url": url, "expires_at": inv.expires_at,
            "emailed": emailed and bool(get_settings().smtp_host)}


@router.delete("/invitations/{inv_id}", status_code=204)
def revoke_invitation(inv_id: uuid.UUID, db: DB, ctx: AdminCtx):
    inv = db.get(Invitation, inv_id)
    if not inv or inv.org_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")
    db.delete(inv)
    db.commit()


# ---------------------------------------------------------------- audit log


@router.get("/audit-log")
def audit_log(db: DB, ctx: Ctx, limit: int = 100):
    if not (ctx.is_admin or ctx.role == "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or auditor access required")
    rows = db.scalars(
        select(AuditLog).where(AuditLog.org_id == ctx.org_id).order_by(AuditLog.seq.desc()).limit(min(limit, 1000))
    )
    return [
        {"id": r.id, "seq": r.seq, "at": r.at, "action": r.action, "entity_type": r.entity_type,
         "entity_id": r.entity_id, "detail": r.detail, "user": r.user.full_name if r.user else "System",
         "ip": r.ip, "hash": r.hash}
        for r in rows
    ]
