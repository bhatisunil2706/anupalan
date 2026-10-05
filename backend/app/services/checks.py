"""One path for every automated check: store the result, keep evidence current, open/close remediation tasks,
and alert the owner when a check starts failing."""
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, Evidence, Task, TestResult, User
from app.services import notify

AUTOMATED_EVIDENCE_DAYS = 7  # automated evidence expires if syncs stop


def record_check(
    db: Session,
    org_id: uuid.UUID,
    *,
    integration_id: uuid.UUID | None,
    source_name: str,
    key: str,
    title: str,
    control_codes: list[str],
    status: str,
    summary: str,
    details: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    details = details or {}
    db.add(TestResult(org_id=org_id, integration_id=integration_id, test_key=key, title=title, status=status,
                      control_codes=control_codes, details={"summary": summary, **details}, run_at=now))
    controls = {c.code: c for c in db.scalars(
        select(Control).where(Control.org_id == org_id, Control.code.in_(control_codes)))}
    source = f"test:{key}"
    for code in control_codes:
        control = controls.get(code)
        if control is None:
            continue
        ev = db.scalar(select(Evidence).where(Evidence.control_id == control.id, Evidence.source == source))
        if status == "pass":
            ev = ev or Evidence(org_id=org_id, control_id=control.id, kind="automated", source=source)
            ev.title = f"{source_name}: {title}"
            ev.description = summary
            ev.data = {"status": status, **details}
            ev.collected_at = now
            ev.valid_until = date.today() + timedelta(days=AUTOMATED_EVIDENCE_DAYS)
            db.add(ev)
        elif ev is not None:
            ev.valid_until = date.today() - timedelta(days=1)  # a failing check invalidates earlier evidence

    open_task = db.scalar(select(Task).where(Task.org_id == org_id, Task.source == source, Task.status != "done"))
    if status == "fail" and open_task is None:
        first = next((controls[c] for c in control_codes if c in controls), None)
        task = Task(org_id=org_id, title=f"Fix: {title}", description=summary, source=source,
                    control_id=first.id if first else None, assignee_id=first.owner_id if first else None,
                    priority="high", due_date=date.today() + timedelta(days=14))
        db.add(task)
        db.flush()
        owner_email = db.scalar(select(User.email).where(User.id == task.assignee_id)) if task.assignee_id else None
        notify.queue(
            db, org_id, key=f"check-failed:{key}:{task.id}", event="check_failed",
            title=f"Check failing: {title}", body=f"{source_name}: {summary}", link="/tasks",
            to=[owner_email] if owner_email else notify.admin_emails(db, org_id), broadcast=True,
        )
    elif status == "pass" and open_task is not None:
        open_task.status = "done"
        open_task.completed_at = now
        open_task.description += "\n\nAutomatically resolved: the check now passes."
