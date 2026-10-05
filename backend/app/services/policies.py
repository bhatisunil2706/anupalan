from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, Evidence, Policy, PolicyTemplate


def render_template(body: str, org_name: str, owner_name: str) -> str:
    return body.replace("{{company}}", org_name).replace("{{owner}}", owner_name)


def create_policy_from_template(db: Session, ctx, tpl: PolicyTemplate, skip_existing: bool = False) -> Policy | None:
    existing = db.scalar(select(Policy).where(Policy.org_id == ctx.org_id, Policy.slug == tpl.slug))
    if existing:
        return None if skip_existing else existing
    policy = Policy(
        org_id=ctx.org_id,
        slug=tpl.slug,
        title=tpl.title,
        body_md=render_template(tpl.body_md, ctx.org.name, ctx.user.full_name),
        control_codes=list(tpl.control_codes),
        owner_id=ctx.user.id,
    )
    db.add(policy)
    db.flush()
    return policy


def approve_policy(db: Session, ctx, policy: Policy) -> None:
    """Approve the current version and attach it as evidence to every mapped control."""
    now = datetime.now(timezone.utc)
    policy.status = "approved"
    policy.approved_by_id = ctx.user.id
    policy.approved_at = now
    tpl = db.scalar(select(PolicyTemplate).where(PolicyTemplate.slug == policy.slug))
    months = tpl.review_months if tpl else 12
    policy.review_due = date.today() + timedelta(days=round(months * 30.4))
    source = f"policy:{policy.id}"
    controls = db.scalars(
        select(Control).where(Control.org_id == ctx.org_id, Control.code.in_(policy.control_codes or []))
    )
    for control in controls:
        ev = db.scalar(select(Evidence).where(Evidence.control_id == control.id, Evidence.source == source))
        ev = ev or Evidence(org_id=ctx.org_id, control_id=control.id, kind="policy", source=source)
        ev.title = f"{policy.title} v{policy.version} (approved)"
        ev.description = f"Approved by {ctx.user.full_name} on {now:%d %b %Y}."
        ev.collected_at = now
        ev.valid_until = policy.review_due
        ev.uploaded_by_id = ctx.user.id
        ev.data = {"policy_id": str(policy.id), "version": policy.version}
        db.add(ev)
