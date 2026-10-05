"""Run integrations: checks, account inventory and HR roster, then cross-source platform checks."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations import REGISTRY
from app.integrations.base import CheckResult, Connector, ConnectorError
from app.models import Account, Integration, Organization
from app.security import decrypt_json
from app.services.checks import record_check
from app.services.people import upsert_people
from app.services.platform_checks import run_platform_checks, verify_review_removals


def build_connector(integration: Integration) -> Connector:
    cls = REGISTRY[integration.provider]
    return cls(integration.config or {}, decrypt_json(integration.secret_encrypted))


def apply_results(db: Session, integration: Integration, results: list[CheckResult]) -> None:
    cls = REGISTRY[integration.provider]
    for res in results:
        tdef = cls.test_def(res.key)
        record_check(db, integration.org_id, integration_id=integration.id, source_name=cls.name, key=res.key,
                     title=tdef.title, control_codes=tdef.control_codes, status=res.status, summary=res.summary,
                     details=res.details)


def sync_accounts(db: Session, integration: Integration, records) -> int:
    now = datetime.now(timezone.utc)
    existing = {a.external_id: a for a in db.scalars(select(Account).where(
        Account.org_id == integration.org_id, Account.provider == integration.provider))}
    seen = set()
    for r in records:
        acc = existing.get(r.external_id) or Account(org_id=integration.org_id, integration_id=integration.id,
                                                     provider=integration.provider, external_id=r.external_id)
        acc.integration_id = integration.id
        acc.email = (r.email or "").lower()
        acc.name = r.name or ""
        acc.is_admin = r.is_admin
        acc.is_active = r.is_active
        acc.mfa_enabled = r.mfa_enabled
        acc.last_login_at = r.last_login_at
        acc.synced_at = now
        db.add(acc)
        seen.add(r.external_id)
    for ext_id, acc in existing.items():
        if ext_id not in seen:
            db.delete(acc)  # account removed in the source system
    db.flush()
    return len(seen)


def sync_integration(db: Session, integration: Integration) -> list[CheckResult]:
    connector = build_connector(integration)
    try:
        results = connector.run()
        accounts = connector.list_accounts() if connector.provides_accounts else None
        people = connector.list_people() if connector.provides_people else None
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
    if accounts is not None:
        sync_accounts(db, integration, accounts)
    if people is not None:
        upsert_people(db, integration.org_id, people, source=integration.provider)
    org = db.get(Organization, integration.org_id)
    run_platform_checks(db, org)
    verify_review_removals(db, org.id)

    integration.status = "connected"
    integration.last_error = ""
    integration.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return results
