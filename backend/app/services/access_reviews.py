"""Access reviews: snapshot accounts from connected systems, route each to the person's manager, record decisions,
verify removals on the next sync, and file the signed-off review as evidence."""
import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations import REGISTRY
from app.models import (
    AccessReview,
    AccessReviewItem,
    Account,
    Control,
    Evidence,
    Membership,
    Person,
    Task,
    User,
)
from app.services import notify, storage

EVIDENCE_DAYS = 92


def system_name(provider: str) -> str:
    return REGISTRY[provider].name if provider in REGISTRY else provider


def create_review(db: Session, ctx, title: str, providers: list[str], due_date: date | None,
                  default_reviewer_id: uuid.UUID | None) -> AccessReview:
    accounts = db.scalars(select(Account).where(Account.org_id == ctx.org_id, Account.provider.in_(providers),
                                                Account.is_active.is_(True))).all()
    if not accounts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No active accounts found for those systems. Connect and sync an integration first.")
    members = {u.email.lower(): u for u in db.scalars(
        select(User).join(Membership, Membership.user_id == User.id).where(Membership.org_id == ctx.org_id))}
    people = {p.email: p for p in db.scalars(select(Person).where(Person.org_id == ctx.org_id))}
    fallback = default_reviewer_id or ctx.user.id

    review = AccessReview(org_id=ctx.org_id, title=title, providers=providers, created_by_id=ctx.user.id,
                          due_date=due_date or date.today() + timedelta(days=14))
    db.add(review)
    db.flush()
    for a in accounts:
        person = people.get(a.email) if a.email else None
        manager = members.get(person.manager_email) if person and person.manager_email else None
        reviewer = manager.id if manager and manager.email.lower() != a.email else fallback
        if reviewer and members.get(a.email) and members[a.email].id == reviewer:
            reviewer = ctx.user.id if ctx.user.id != reviewer else fallback  # nobody reviews their own access
        db.add(AccessReviewItem(
            review_id=review.id, org_id=ctx.org_id, account_id=a.id, provider=a.provider,
            external_id=a.external_id, email=a.email, name=a.name, is_admin=a.is_admin,
            person_status=person.status if person else "unknown", reviewer_id=reviewer,
        ))
    db.flush()
    reviewer_ids = set(db.scalars(select(AccessReviewItem.reviewer_id).where(AccessReviewItem.review_id == review.id)))
    for rid in reviewer_ids:
        email = db.scalar(select(User.email).where(User.id == rid))
        count = db.scalar(select(func.count()).select_from(AccessReviewItem).where(
            AccessReviewItem.review_id == review.id, AccessReviewItem.reviewer_id == rid))
        if email:
            notify.queue(db, ctx.org_id, key=f"ar:{review.id}:{rid}:assigned", event="access_review", to=[email],
                         title=f"Please review {count} accounts: {title}",
                         body=f"Decide whether each person still needs their access by {review.due_date:%d %b %Y}.",
                         link=f"/access-reviews/{review.id}")
    # Close the reminder task that asked for this review.
    for t in db.scalars(select(Task).where(Task.org_id == ctx.org_id, Task.source.startswith("access-review-due:"),
                                           Task.status != "done")):
        t.status, t.completed_at = "done", datetime.now(timezone.utc)
    return review


def decide(db: Session, ctx, item: AccessReviewItem, decision: str, note: str) -> None:
    review = item.review
    if review.status != "open":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This review is already completed")
    if item.reviewer_id != ctx.user.id and not ctx.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is assigned to another reviewer")
    if decision == "revoke" and not note.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add a short reason when removing access")
    item.decision, item.note = decision, note.strip()
    item.decided_by_id, item.decided_at = ctx.user.id, datetime.now(timezone.utc)
    source = f"review-item:{item.id}"
    task = db.scalar(select(Task).where(Task.org_id == ctx.org_id, Task.source == source))
    if decision == "revoke":
        acc = db.get(Account, item.account_id) if item.account_id else None
        if acc is None or not acc.is_active:
            item.removal_verified_at = item.decided_at
        elif task is None:
            who = item.email or item.name
            db.add(Task(org_id=ctx.org_id, source=source, title=f"Remove {who} from {system_name(item.provider)}",
                        description=f"Access review '{review.title}': {item.note}\nThe task closes automatically once "
                                    "the account is removed or disabled and the integration syncs.",
                        assignee_id=review.created_by_id, priority="high",
                        due_date=date.today() + timedelta(days=3)))
    elif task is not None and task.status != "done":
        task.status, task.completed_at = "done", datetime.now(timezone.utc)
        task.description += "\n\nClosed: the reviewer changed the decision to keep."


def export_csv(db: Session, review: AccessReview) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["System", "Account", "Email", "Admin", "Employee status", "Reviewer", "Decision", "Reason",
                "Decided by", "Decided at (UTC)", "Removal verified at (UTC)"])
    for i in sorted(review.items, key=lambda i: (i.provider, i.email or i.name)):
        w.writerow([system_name(i.provider), i.name, i.email, "yes" if i.is_admin else "no", i.person_status,
                    i.reviewer.full_name if i.reviewer else "", i.decision, i.note,
                    i.decided_by.full_name if i.decided_by else "",
                    i.decided_at.strftime("%Y-%m-%d %H:%M") if i.decided_at else "",
                    i.removal_verified_at.strftime("%Y-%m-%d %H:%M") if i.removal_verified_at else ""])
    return buf.getvalue().encode()


def complete(db: Session, ctx, review: AccessReview) -> Evidence | None:
    pending = sum(1 for i in review.items if i.decision == "pending")
    if pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{pending} accounts still need a decision")
    now = datetime.now(timezone.utc)
    review.status, review.completed_at = "completed", now
    control = db.scalar(select(Control).where(Control.org_id == ctx.org_id, Control.code == "ACC-05"))
    if control is None:
        return None
    key, name, size = storage.save_bytes(ctx.org_id, f"access-review-{now:%Y-%m-%d}.csv", export_csv(db, review))
    kept = sum(1 for i in review.items if i.decision == "keep")
    revoked = sum(1 for i in review.items if i.decision == "revoke")
    ev = Evidence(
        org_id=ctx.org_id, control_id=control.id, kind="file", source=f"access-review:{review.id}",
        title=f"Access review: {review.title}", file_key=key, file_name=name, size_bytes=size,
        content_type="text/csv", uploaded_by_id=ctx.user.id, valid_until=date.today() + timedelta(days=EVIDENCE_DAYS),
        description=f"{len(review.items)} accounts across {', '.join(system_name(p) for p in review.providers)}: "
                    f"{kept} kept, {revoked} removed. Completed by {ctx.user.full_name}.",
    )
    db.add(ev)
    return ev
