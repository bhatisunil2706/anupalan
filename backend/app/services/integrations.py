"""Run integration checks and turn results into evidence and remediation tasks."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import REGISTRY
from app.integrations.base import CheckResult, Connector, ConnectorError
from app.models import Control, Evidence, Integration, Task, TestResult
from app.security import decrypt_json

AUTOMATED_EVIDENCE_DAYS = 7  # automated evidence expires if syncs stop


def build_connector(integration: Integration) -> Connector:
    cls = REGISTRY[integration.provider]
    return cls(integration.config or {}, decrypt_json(integration.secret_encrypted))


def apply_results(db: Session, integration: Integration, results: list[CheckResult]) -> None:
    cls = REGISTRY[integration.provider]
    org_id = integration.org_id
    now = datetime.now(timezone.utc)
    controls = {c.code: c for c in db.scalars(select(Control).where(Control.org_id == org_id))}

    for res in results:
        tdef = cls.test_def(res.key)
        db.add(TestResult(org_id=org_id, integration_id=integration.id, test_key=res.key, title=tdef.title,
                          status=res.status, control_codes=tdef.control_codes,
                          details={"summary": res.summary, **res.details}, run_at=now))
        source = f"test:{res.key}"
        for code in tdef.control_codes:
            control = controls.get(code)
            if control is None:
                continue
            ev = db.scalar(select(Evidence).where(Evidence.control_id == control.id, Evidence.source == source))
            if res.status == "pass":
                ev = ev or Evidence(org_id=org_id, control_id=control.id, kind="automated", source=source)
                ev.title = f"{cls.name}: {tdef.title}"
                ev.description = res.summary
                ev.data = {"status": res.status, **res.details}
                ev.collected_at = now
                ev.valid_until = date.today() + timedelta(days=AUTOMATED_EVIDENCE_DAYS)
                db.add(ev)
            elif ev is not None:
                ev.valid_until = date.today() - timedelta(days=1)  # failing check invalidates prior evidence

        open_task = db.scalar(
            select(Task).where(Task.org_id == org_id, Task.source == source, Task.status != "done")
        )
        if res.status == "fail" and open_task is None:
            first = next((controls[c] for c in tdef.control_codes if c in controls), None)
            db.add(Task(org_id=org_id, title=f"Fix: {tdef.title}", description=res.summary, source=source,
                        control_id=first.id if first else None, assignee_id=first.owner_id if first else None,
                        priority="high", due_date=date.today() + timedelta(days=14)))
        elif res.status == "pass" and open_task is not None:
            open_task.status = "done"
            open_task.completed_at = now
            open_task.description += "\n\nAutomatically resolved: the check now passes."


def sync_integration(db: Session, integration: Integration) -> list[CheckResult]:
    connector = build_connector(integration)
    try:
        results = connector.run()
    except ConnectorError as e:
        integration.status = "error"
        integration.last_error = str(e)
        db.commit()
        raise
    except Exception as e:  # unexpected provider errors
        integration.status = "error"
        integration.last_error = f"{type(e).__name__}: {e}"[:1000]
        db.commit()
        raise ConnectorError(integration.last_error) from e
    apply_results(db, integration, results)
    integration.status = "connected"
    integration.last_error = ""
    integration.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return results
