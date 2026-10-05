"""Scheduled automation: deadline reminders and recurring compliance tasks.

Runs from the worker every few minutes. Every action is idempotent (dedupe keys / task sources), so running it
often is safe.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AccessReview,
    AccessReviewItem,
    Account,
    Control,
    Evidence,
    Incident,
    Organization,
    Policy,
    RightsRequest,
    Task,
    User,
    Vendor,
)
from app.services import notify

RENEW_WINDOW_DAYS = 14


def _email(db: Session, user_id) -> str | None:
    return db.scalar(select(User.email).where(User.id == user_id)) if user_id else None


def _ensure_task(db: Session, org_id, source: str, prefix: str, **fields) -> Task | None:
    """Create a task unless one with the same prefix is still open. Returns the new task or None."""
    if db.scalar(select(Task.id).where(Task.org_id == org_id, Task.source.startswith(prefix),
                                       Task.status != "done").limit(1)):
        return None
    if db.scalar(select(Task.id).where(Task.org_id == org_id, Task.source == source).limit(1)):
        return None  # already created (and completed) for this cycle
    t = Task(org_id=org_id, source=source, **fields)
    db.add(t)
    db.flush()
    return t


def _task_created(db: Session, org: Organization, t: Task) -> None:
    to = [e for e in [_email(db, t.assignee_id)] if e] or notify.admin_emails(db, org.id)
    notify.queue(db, org.id, key=f"task:{t.id}:created", event="task_created", title=t.title,
                 body=t.description, link="/tasks", to=to)


def incident_reminders(db: Session, org: Organization, now: datetime) -> None:
    admins = notify.admin_emails(db, org.id)
    for i in db.scalars(select(Incident).where(Incident.org_id == org.id, Incident.status != "closed")):
        to = sorted(set(admins + [e for e in [_email(db, i.lead_id)] if e]))
        label = f"INC-{i.number} {i.title}"
        link = f"/incidents/{i.id}"
        if i.certin_due_at and not i.certin_reported_at:
            if i.certin_due_at <= now:
                notify.queue(db, org.id, key=f"inc:{i.id}:certin:overdue", event="deadline", broadcast=True, to=to,
                             title=f"CERT-In report overdue: {label}", link=link,
                             body="The 6-hour CERT-In reporting deadline has passed.")
            elif i.certin_due_at - now <= timedelta(hours=2):
                notify.queue(db, org.id, key=f"inc:{i.id}:certin:2h", event="deadline", broadcast=True, to=to,
                             title=f"CERT-In report due within 2 hours: {label}", link=link)
        if i.dpb_due_at and not i.dpb_detailed_reported_at:
            if i.dpb_due_at <= now:
                notify.queue(db, org.id, key=f"inc:{i.id}:dpb:overdue", event="deadline", broadcast=True, to=to,
                             title=f"Data Protection Board report overdue: {label}", link=link)
            elif i.dpb_due_at - now <= timedelta(hours=24):
                notify.queue(db, org.id, key=f"inc:{i.id}:dpb:24h", event="deadline", broadcast=True, to=to,
                             title=f"Board detailed report due within 24 hours: {label}", link=link)


def request_reminders(db: Session, org: Organization, now: datetime) -> None:
    for r in db.scalars(select(RightsRequest).where(RightsRequest.org_id == org.id,
                                                     RightsRequest.status.not_in(("completed", "rejected")))):
        to = [e for e in [_email(db, r.assignee_id)] if e] or notify.admin_emails(db, org.id)
        label = f"DPR-{r.number} ({r.request_type.replace('_', ' ')}) from {r.requester_name}"
        if r.due_at <= now:
            notify.queue(db, org.id, key=f"rr:{r.id}:overdue", event="deadline", to=to, broadcast=True,
                         title=f"Rights request overdue: {label}", link="/dpdp/requests")
        elif r.due_at - now <= timedelta(days=3):
            notify.queue(db, org.id, key=f"rr:{r.id}:3d", event="deadline", to=to,
                         title=f"Rights request due in 3 days: {label}", link="/dpdp/requests")


def task_reminders(db: Session, org: Organization, today: date) -> None:
    for t in db.scalars(select(Task).where(Task.org_id == org.id, Task.status != "done",
                                           Task.due_date.is_not(None), Task.assignee_id.is_not(None))):
        to = [e for e in [_email(db, t.assignee_id)] if e]
        if t.due_date < today:
            notify.queue(db, org.id, key=f"task:{t.id}:overdue", event="task_due", to=to,
                         title=f"Overdue: {t.title}", link="/tasks")
        elif t.due_date == today + timedelta(days=1):
            notify.queue(db, org.id, key=f"task:{t.id}:due:{t.due_date}", event="task_due", to=to,
                         title=f"Due tomorrow: {t.title}", link="/tasks")


def evidence_renewals(db: Session, org: Organization, today: date) -> None:
    """Create a task before an implemented control's evidence runs out (manual and policy evidence only)."""
    horizon = today + timedelta(days=RENEW_WINDOW_DAYS)
    for c in db.scalars(select(Control).where(Control.org_id == org.id, Control.status == "implemented")):
        latest = db.scalar(select(func.max(Evidence.valid_until)).where(
            Evidence.control_id == c.id, Evidence.kind.in_(("file", "link", "note", "policy"))))
        automated = db.scalar(select(Evidence.id).where(
            Evidence.control_id == c.id, Evidence.kind == "automated", Evidence.valid_until >= today).limit(1))
        if automated or c.frequency in ("once",):
            continue
        if latest is None:
            t = _ensure_task(db, org.id, f"recurring:{c.id}:missing", f"recurring:{c.id}:",
                             title=f"Add evidence: {c.code} {c.title}", control_id=c.id, assignee_id=c.owner_id,
                             priority="medium", due_date=today + timedelta(days=7),
                             description="This control is marked implemented but has no current evidence.")
        elif latest <= horizon:
            t = _ensure_task(db, org.id, f"recurring:{c.id}:{latest}", f"recurring:{c.id}:",
                             title=f"Renew evidence: {c.code} {c.title}", control_id=c.id, assignee_id=c.owner_id,
                             priority="medium", due_date=latest,
                             description=f"Evidence for this {c.frequency} control expires on {latest:%d %b %Y}. "
                                         "Upload fresh evidence before then.")
        else:
            t = None
        if t:
            _task_created(db, org, t)


def review_cycle_tasks(db: Session, org: Organization, today: date) -> None:
    for v in db.scalars(select(Vendor).where(Vendor.org_id == org.id, Vendor.status != "offboarded",
                                             Vendor.next_review_date.is_not(None),
                                             Vendor.next_review_date <= today + timedelta(days=RENEW_WINDOW_DAYS))):
        t = _ensure_task(db, org.id, f"vendor-review:{v.id}:{v.next_review_date}", f"vendor-review:{v.id}:",
                         title=f"Review vendor: {v.name}", assignee_id=v.owner_id, priority="medium",
                         due_date=v.next_review_date,
                         description="Reassess the vendor's security and check its certificates and DPA are current.")
        if t:
            _task_created(db, org, t)
    for p in db.scalars(select(Policy).where(Policy.org_id == org.id, Policy.status == "approved",
                                             Policy.review_due.is_not(None),
                                             Policy.review_due <= today + timedelta(days=30))):
        t = _ensure_task(db, org.id, f"policy-review:{p.id}:{p.review_due}", f"policy-review:{p.id}:",
                         title=f"Annual review: {p.title}", assignee_id=p.owner_id, priority="medium",
                         due_date=p.review_due,
                         description="Review the policy, update it if needed and approve the new version.")
        if t:
            _task_created(db, org, t)
    # Quarterly access review, once the org has synced accounts.
    if db.scalar(select(Account.id).where(Account.org_id == org.id).limit(1)):
        last = db.scalar(select(func.max(AccessReview.created_at)).where(AccessReview.org_id == org.id))
        if last is None or last.date() < today - timedelta(days=90):
            quarter = f"{today.year}-Q{(today.month - 1) // 3 + 1}"
            t = _ensure_task(db, org.id, f"access-review-due:{quarter}", "access-review-due:",
                             title="Start the quarterly access review", priority="medium",
                             due_date=today + timedelta(days=14),
                             description="Go to Access reviews and start a review of the connected systems.")
            if t:
                _task_created(db, org, t)


def access_review_reminders(db: Session, org: Organization, today: date) -> None:
    for review in db.scalars(select(AccessReview).where(AccessReview.org_id == org.id,
                                                        AccessReview.status == "open",
                                                        AccessReview.due_date.is_not(None),
                                                        AccessReview.due_date <= today + timedelta(days=3))):
        reviewers = set(db.scalars(select(AccessReviewItem.reviewer_id).where(
            AccessReviewItem.review_id == review.id, AccessReviewItem.decision == "pending")))
        for rid in reviewers:
            email = _email(db, rid)
            if email:
                notify.queue(db, org.id, key=f"ar:{review.id}:{rid}:due", event="access_review", to=[email],
                             title=f"Access review due {review.due_date:%d %b}: {review.title}",
                             link=f"/access-reviews/{review.id}")


def run_reminders(db: Session, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    for org in db.scalars(select(Organization).where(Organization.onboarded_at.is_not(None))):
        incident_reminders(db, org, now)
        request_reminders(db, org, now)
        task_reminders(db, org, today)
        evidence_renewals(db, org, today)
        review_cycle_tasks(db, org, today)
        access_review_reminders(db, org, today)
        db.commit()
