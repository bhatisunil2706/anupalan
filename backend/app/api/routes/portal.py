"""Public DPDP rights-request portal (no login) and its admin settings."""
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, AdminCtx
from app.models import Organization, PortalVerification, RightsRequest
from app.security import hash_token, new_token
from app.services import audit, notify

router = APIRouter()

REQUEST_TYPES = {
    "access": "Get a summary of my personal data",
    "correction": "Correct or update my personal data",
    "erasure": "Erase my personal data",
    "consent_withdrawal": "Withdraw my consent",
    "nomination": "Nominate someone to exercise my rights",
    "grievance": "Raise a grievance",
}
VERIFY_HOURS = 24
_HITS: dict[str, deque] = defaultdict(deque)
LIMIT_PER_HOUR = 5
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])$")


def _rate_limited(key: str) -> bool:
    q, now = _HITS[key], time.monotonic()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= LIMIT_PER_HOUR:
        return True
    q.append(now)
    return False


# ---------------------------------------------------------------- admin settings


class PortalSettingsIn(BaseModel):
    portal_enabled: bool
    portal_slug: str = Field(min_length=3, max_length=60)
    privacy_contact_name: str = Field(min_length=1, max_length=200)
    privacy_contact_email: EmailStr


def _settings_out(org: Organization) -> dict:
    return {"portal_enabled": org.portal_enabled, "portal_slug": org.portal_slug or "",
            "privacy_contact_name": org.privacy_contact_name, "privacy_contact_email": org.privacy_contact_email,
            "public_url": f"{get_settings().public_url.rstrip('/')}/p/{org.portal_slug}" if org.portal_slug else ""}


@router.get("/org/portal", tags=["portal"])
def portal_settings(ctx: AdminCtx):
    return _settings_out(ctx.org)


@router.put("/org/portal", tags=["portal"])
def update_portal(body: PortalSettingsIn, db: DB, ctx: AdminCtx):
    slug = body.portal_slug.strip().lower()
    if not SLUG_RE.match(slug):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use lowercase letters, numbers and dashes for the address")
    taken = db.scalar(select(Organization.id).where(Organization.portal_slug == slug, Organization.id != ctx.org_id))
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "That address is already taken")
    org = ctx.org
    org.portal_enabled, org.portal_slug = body.portal_enabled, slug
    org.privacy_contact_name, org.privacy_contact_email = body.privacy_contact_name.strip(), body.privacy_contact_email
    audit.record(db, ctx, "portal.updated", org, enabled=org.portal_enabled)
    db.commit()
    return _settings_out(org)


# ---------------------------------------------------------------- public


def _org(db, slug: str) -> Organization:
    org = db.scalar(select(Organization).where(Organization.portal_slug == slug.lower()))
    if not org or not org.portal_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This privacy request page is not available")
    return org


@router.get("/public/portal/{slug}", tags=["public"])
def portal_info(slug: str, db: DB):
    org = _org(db, slug)
    return {"org_name": org.name, "contact_name": org.privacy_contact_name,
            "contact_email": org.privacy_contact_email, "request_types": REQUEST_TYPES}


class PublicRequestIn(BaseModel):
    request_type: str
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    details: str = Field(default="", max_length=5000)
    website: str = ""  # honeypot: must stay empty


@router.post("/public/portal/{slug}/requests", status_code=202, tags=["public"])
def submit_request(slug: str, body: PublicRequestIn, request: Request, db: DB):
    org = _org(db, slug)
    if body.request_type not in REQUEST_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a request type")
    ip = request.client.host if request.client else ""
    if body.website or _rate_limited(f"{ip}|{slug}") or _rate_limited(f"{body.email.lower()}|{slug}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Please try again later.")
    token, token_hash = new_token()
    db.add(PortalVerification(
        org_id=org.id, token_hash=token_hash, email=body.email.lower(), ip=ip,
        payload={"request_type": body.request_type, "full_name": body.full_name.strip(), "details": body.details},
        expires_at=datetime.now(timezone.utc) + timedelta(hours=VERIFY_HOURS),
    ))
    db.commit()
    link = f"{get_settings().public_url.rstrip('/')}/p/{org.portal_slug}/verify?token={token}"
    try:
        _send_verification(org, body, link)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "We couldn't send the confirmation email. Please try again later.") from e
    out = {"status": "verification_sent"}
    if not get_settings().smtp_host and not get_settings().is_production:
        out["dev_verify_url"] = link  # no email configured in development: show the link so the flow is testable
    return out


def _send_verification(org: Organization, body: "PublicRequestIn", link: str) -> None:
    notify.send_email(
        [body.email], f"Confirm your privacy request to {org.name}",
        f"Hello {body.full_name},\n\nPlease confirm your request ({REQUEST_TYPES[body.request_type].lower()}) by "
        f"opening this link within {VERIFY_HOURS} hours:\n\n{link}\n\nIf you didn't make this request, ignore this "
        f"email.\n\n{org.name} privacy contact: {org.privacy_contact_name} <{org.privacy_contact_email}>")


class VerifyIn(BaseModel):
    token: str


@router.post("/public/portal/{slug}/verify", tags=["public"])
def verify_request(slug: str, body: VerifyIn, db: DB):
    org = _org(db, slug)
    v = db.scalar(select(PortalVerification).where(PortalVerification.token_hash == hash_token(body.token),
                                                   PortalVerification.org_id == org.id))
    if not v or v.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is invalid or has expired. Please submit again.")
    if v.used_at:
        r = db.scalar(select(RightsRequest).where(RightsRequest.org_id == org.id,
                                                  RightsRequest.requester_email == v.email)
                      .order_by(RightsRequest.received_at.desc()))
        return {"status": "already_confirmed", "reference": f"DPR-{r.number}" if r else None}
    now = datetime.now(timezone.utc)
    sla = min(org.rights_request_sla_days, 90)
    number = (db.scalar(select(func.max(RightsRequest.number)).where(RightsRequest.org_id == org.id)) or 0) + 1
    rr = RightsRequest(
        org_id=org.id, number=number, request_type=v.payload["request_type"],
        requester_name=v.payload["full_name"], requester_email=v.email,
        details=v.payload.get("details", ""), channel="web portal (email verified)", received_at=now,
        due_at=now + timedelta(days=sla), legal_due_at=now + timedelta(days=90),
    )
    db.add(rr)
    v.used_at = now
    db.flush()
    notify.queue(db, org.id, key=f"rr:{rr.id}:new", event="rights_request", broadcast=True,
                 to=sorted(set(notify.admin_emails(db, org.id) + ([org.privacy_contact_email]
                                                                   if org.privacy_contact_email else []))),
                 title=f"New rights request DPR-{number}: {rr.request_type.replace('_', ' ')}",
                 body=f"From {rr.requester_name} ({rr.requester_email}), email verified. Due {rr.due_at:%d %b %Y}.",
                 link="/dpdp/requests")
    db.commit()
    return {"status": "confirmed", "reference": f"DPR-{number}", "due_days": sla,
            "contact_email": org.privacy_contact_email}
