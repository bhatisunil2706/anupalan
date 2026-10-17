"""Phishing simulation campaigns (admin) and the public teachable-moment page that a click lands on."""
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import ratelimit
from app.db import set_tenant, system_session
from app.deps import DB, AdminCtx, get_owned
from app.models import Organization, PhishingCampaign, PhishingTarget
from app.request_context import client_ip
from app.security import hash_token
from app.services import audit
from app.services import phishing as ph

router = APIRouter(tags=["phishing"])


def _campaign_out(db, c: PhishingCampaign, full: bool = False) -> dict:
    tpl = ph.TEMPLATES.get(c.template_slug, {})
    out = {"id": c.id, "name": c.name, "template_slug": c.template_slug, "template_name": tpl.get("name", ""),
           "difficulty": tpl.get("difficulty", ""), "departments": c.departments or [], "status": c.status,
           "enroll_clickers": c.enroll_clickers, "sent_at": c.sent_at, "closed_at": c.closed_at,
           "created_at": c.created_at}
    if c.status == "draft":
        out["eligible"] = len(ph.eligible_targets(db, c.org_id, c.departments or []))
    r = ph.results(db, c)
    out.update({"sent": r["sent"], "clicked": r["clicked"], "click_rate": r["click_rate"]})
    if full:
        out.update({"results": r, "subject": tpl.get("subject"), "sender": tpl.get("sender"),
                    "red_flags": tpl.get("red_flags", [])})
    return out


@router.get("/training/phishing/templates")
def templates(ctx: AdminCtx):
    return ph.template_list()


@router.get("/training/phishing/campaigns")
def campaigns(db: DB, ctx: AdminCtx):
    rows = db.scalars(select(PhishingCampaign).where(PhishingCampaign.org_id == ctx.org_id)
                      .order_by(PhishingCampaign.created_at.desc())).all()
    return [_campaign_out(db, c) for c in rows]


class CampaignIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    template_slug: str
    departments: list[str] = Field(default_factory=list, max_length=50)
    enroll_clickers: bool = True


@router.post("/training/phishing/campaigns", status_code=201)
def create_campaign(body: CampaignIn, db: DB, ctx: AdminCtx):
    if body.template_slug not in ph.TEMPLATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown template")
    c = PhishingCampaign(org_id=ctx.org_id, name=body.name.strip(), template_slug=body.template_slug,
                         departments=sorted({d.strip() for d in body.departments if d.strip()}),
                         enroll_clickers=body.enroll_clickers, created_by_id=ctx.user.id)
    db.add(c)
    db.flush()
    audit.record(db, ctx, "phishing.campaign_created", c, template=c.template_slug)
    db.commit()
    return _campaign_out(db, c, full=True)


@router.get("/training/phishing/campaigns/{campaign_id}")
def campaign(campaign_id: uuid.UUID, db: DB, ctx: AdminCtx):
    return _campaign_out(db, get_owned(db, PhishingCampaign, campaign_id, ctx), full=True)


def _send(campaign_id: uuid.UUID, org_id: uuid.UUID) -> None:
    with system_session() as db:
        set_tenant(db, org_id=org_id)
        c = db.get(PhishingCampaign, campaign_id)
        if c and c.status == "sending":
            ph.launch(db, c)
            db.commit()


@router.post("/training/phishing/campaigns/{campaign_id}/launch")
def launch(campaign_id: uuid.UUID, background: BackgroundTasks, db: DB, ctx: AdminCtx):
    c = get_owned(db, PhishingCampaign, campaign_id, ctx)
    if c.status != "draft":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This campaign has already been sent")
    n = len(ph.eligible_targets(db, ctx.org_id, c.departments or []))
    if not n:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No one to send to. Targets must be on your company's email "
                                                         "domains; add people or verify a domain.")
    c.status = "sending"
    audit.record(db, ctx, "phishing.campaign_launched", c, targets=n)
    db.commit()
    background.add_task(_send, c.id, ctx.org_id)
    return {**_campaign_out(db, c), "targets": n}


@router.post("/training/phishing/campaigns/{campaign_id}/close")
def close(campaign_id: uuid.UUID, db: DB, ctx: AdminCtx):
    from datetime import datetime, timezone

    c = get_owned(db, PhishingCampaign, campaign_id, ctx)
    if c.status not in ("sent", "sending"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only sent campaigns can be closed")
    c.status, c.closed_at = "closed", datetime.now(timezone.utc)
    audit.record(db, ctx, "phishing.campaign_closed", c)
    db.commit()
    return _campaign_out(db, c)


@router.delete("/training/phishing/campaigns/{campaign_id}", status_code=204)
def delete_campaign(campaign_id: uuid.UUID, db: DB, ctx: AdminCtx):
    c = get_owned(db, PhishingCampaign, campaign_id, ctx)
    if c.status != "draft":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sent campaigns are kept as training evidence; close it "
                                                         "instead")
    db.delete(c)
    db.commit()


# ================================================================ public landing page


def _target(db, token: str) -> PhishingTarget:
    ratelimit.enforce("phish", client_ip.get(), 120, 15 * 60)
    set_tenant(db, rls_bypass=True)  # the link token identifies the organisation
    t = db.scalar(select(PhishingTarget).where(PhishingTarget.token_hash == hash_token(token)))
    set_tenant(db, rls_bypass=False)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link isn't valid")
    set_tenant(db, org_id=t.org_id)
    return t


@router.get("/public/phish/{token}")
def landing(token: str, db: DB):
    """Content for the teachable-moment page. Fetching it does not count as a click: link scanners in email
    gateways open links automatically, so the page itself posts the click after it loads in a browser."""
    t = _target(db, token)
    c = db.get(PhishingCampaign, t.campaign_id)
    org = db.get(Organization, t.org_id)
    tpl = ph.TEMPLATES[c.template_slug]
    return {"org_name": org.name, "subject": tpl["subject"], "sender": tpl["sender"], "red_flags": tpl["red_flags"],
            "enrolled": c.enroll_clickers}


@router.post("/public/phish/{token}/click", status_code=204)
def click(token: str, db: DB):
    t = _target(db, token)
    ph.record_click(db, token)
    audit.write(db, org_id=t.org_id, user_id=None, action="phishing.clicked", entity=None,
                detail={"campaign": str(t.campaign_id)})
    db.commit()
