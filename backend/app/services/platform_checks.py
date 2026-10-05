"""Checks that combine several sources, e.g. HR roster x identity accounts."""
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import REGISTRY
from app.models import AccessReviewItem, Account, Organization, Person, Task
from app.services.checks import record_check

LEAVER_GRACE_DAYS = 1  # access must be removed within 24 hours of exit

LEAVER_CHECK = {
    "key": "platform.leaver_access",
    "title": "Leavers have no active accounts",
    "control_codes": ["ACC-02", "HR-05"],
}


def leaver_findings(db: Session, org_id: uuid.UUID, today: date | None = None) -> tuple[list[dict], int, int]:
    """Return (active accounts belonging to people who left more than a day ago, leavers checked, accounts checked)."""
    today = today or date.today()
    leavers = {
        p.email: p for p in db.scalars(select(Person).where(Person.org_id == org_id, Person.status == "exited"))
        if p.exit_date is None or p.exit_date <= today - timedelta(days=LEAVER_GRACE_DAYS)
    }
    accounts = db.scalars(select(Account).where(Account.org_id == org_id, Account.is_active.is_(True))).all()
    findings = []
    for a in accounts:
        p = leavers.get(a.email)
        if a.email and p:
            findings.append({
                "email": a.email, "name": p.full_name or a.name,
                "system": REGISTRY[a.provider].name if a.provider in REGISTRY else a.provider,
                "exit_date": p.exit_date.isoformat() if p.exit_date else None,
                "days_since_exit": (today - p.exit_date).days if p.exit_date else None,
            })
    return findings, len(leavers), len(accounts)


def run_platform_checks(db: Session, org: Organization) -> None:
    has_roster = db.scalar(select(Person.id).where(Person.org_id == org.id).limit(1)) is not None
    has_accounts = db.scalar(select(Account.id).where(Account.org_id == org.id).limit(1)) is not None
    if not (has_roster and has_accounts):
        return
    findings, leavers, accounts = leaver_findings(db, org.id)
    if findings:
        names = ", ".join(f"{f['email']} ({f['system']})" for f in findings[:5])
        more = f" and {len(findings) - 5} more" if len(findings) > 5 else ""
        n = len(findings)
        summary = (f"{n} active {'account belongs' if n == 1 else 'accounts belong'} to "
                   f"{'someone who has' if n == 1 else 'people who have'} left: {names}{more}")
    else:
        summary = f"No active accounts for {leavers} leavers across {accounts} accounts"
    record_check(db, org.id, integration_id=None, source_name="HR cross-check", key=LEAVER_CHECK["key"],
                 title=LEAVER_CHECK["title"], control_codes=LEAVER_CHECK["control_codes"],
                 status="fail" if findings else "pass", summary=summary, details={"accounts": findings[:200]})


def verify_review_removals(db: Session, org_id: uuid.UUID) -> int:
    """Mark access-review revocations as verified once the account is gone or disabled in the source system."""
    now = datetime.now(timezone.utc)
    verified = 0
    items = db.scalars(select(AccessReviewItem).where(
        AccessReviewItem.org_id == org_id, AccessReviewItem.decision == "revoke",
        AccessReviewItem.removal_verified_at.is_(None)))
    for item in items:
        acc = db.get(Account, item.account_id) if item.account_id else None
        if acc is None or not acc.is_active:
            item.removal_verified_at = now
            verified += 1
            task = db.scalar(select(Task).where(Task.org_id == org_id, Task.source == f"review-item:{item.id}",
                                                Task.status != "done"))
            if task:
                task.status, task.completed_at = "done", now
                task.description += "\n\nVerified automatically: the account is no longer active."
    return verified
