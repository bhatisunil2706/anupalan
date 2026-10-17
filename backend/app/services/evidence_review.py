"""Second-person review of uploaded evidence.

Uploaded files, links and notes start as "pending" when the organisation requires review (the default). A different
person (an admin or owner, or the control's owner) approves or rejects them; only approved evidence makes a control
pass. Evidence collected by integrations or produced by the platform is approved automatically, because no one could
have chosen what it shows. In a one-person organisation the uploader may approve their own evidence; it is then
marked as self-approved so the auditor can see it.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, Evidence, Membership, User
from app.services import notify

MANUAL_KINDS = ("file", "link", "note")
REVIEWER_ROLES = ("owner", "admin")


def trust(ev: Evidence) -> str:
    """automated: collected from a connected system; platform: produced by a workflow here; uploaded: by a person."""
    if ev.kind == "automated":
        return "automated"
    if ev.kind in MANUAL_KINDS and (ev.source or "manual") == "manual":
        return "uploaded"
    return "platform"


def needs_review(org, ev: Evidence) -> bool:
    return bool(org.require_evidence_review) and trust(ev) == "uploaded"


def _reviewers(db: Session, org_id: uuid.UUID, control: Control) -> set[uuid.UUID]:
    ids = set(db.scalars(select(Membership.user_id).where(Membership.org_id == org_id,
                                                          Membership.role.in_(REVIEWER_ROLES))))
    if control.owner_id:
        role = db.scalar(select(Membership.role).where(Membership.org_id == org_id,
                                                       Membership.user_id == control.owner_id))
        if role and role != "auditor":
            ids.add(control.owner_id)
    return ids


def permission(db: Session, ctx, ev: Evidence, control: Control) -> tuple[bool, bool, str]:
    """(allowed, would_be_self_approval, reason if not allowed)"""
    if ev.review_status != "pending":
        return False, False, "This evidence has already been reviewed"
    reviewers = _reviewers(db, ctx.org_id, control)
    if ctx.user.id not in reviewers:
        return False, False, "Only the control owner or an admin can review evidence"
    if ev.uploaded_by_id == ctx.user.id:
        if reviewers - {ctx.user.id}:
            return False, False, "Someone else must review evidence you added"
        return True, True, ""
    return True, False, ""


def decide(db: Session, ctx, ev: Evidence, control: Control, approve: bool, note: str) -> None:
    allowed, self_approval, reason = permission(db, ctx, ev, control)
    if not allowed:
        raise PermissionError(reason)
    ev.review_status = "approved" if approve else "rejected"
    ev.reviewed_by_id, ev.reviewed_at = ctx.user.id, datetime.now(timezone.utc)
    ev.review_note, ev.self_approved = note.strip()[:2000], self_approval
    if not approve and ev.uploaded_by_id and ev.uploaded_by_id != ctx.user.id:
        uploader = db.get(User, ev.uploaded_by_id)
        if uploader:
            notify.queue(db, ctx.org_id, key=f"evidence-rejected:{ev.id}", event="evidence_rejected",
                         title=f"Evidence sent back for {control.code}: {ev.title}",
                         body=f"{ctx.user.full_name or ctx.user.email} sent back your evidence.\n\nReason: {note}",
                         link=f"/controls/{control.id}", to=[uploader.email])


def notify_pending(db: Session, ctx, ev: Evidence, control: Control) -> None:
    """Tell the people who can review it, except the uploader."""
    reviewers = _reviewers(db, ctx.org_id, control) - {ctx.user.id}
    if control.owner_id in reviewers:
        reviewers = {control.owner_id}  # the control owner first; admins see it in the review queue
    emails = [e for e in db.scalars(select(User.email).where(User.id.in_(reviewers)))] if reviewers else []
    if emails:
        notify.queue(db, ctx.org_id, key=f"evidence-pending:{ev.id}", event="evidence_pending",
                     title=f"Evidence to review for {control.code}: {ev.title}",
                     body=f"{ctx.user.full_name or ctx.user.email} added evidence for {control.code} {control.title}.",
                     link="/evidence/review", to=emails)
