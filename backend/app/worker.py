"""Background worker.

- every minute: deliver queued notifications (email, Slack, Teams)
- every 15 minutes: deadline reminders and recurring compliance tasks
- every 6 hours: sync every connected integration

Run with:  python -m app.worker            (loops forever)
           python -m app.worker --once     (single pass of everything, e.g. from cron)
"""
import argparse
import logging
import time

from sqlalchemy import select

from app.db import system_session
from app.integrations.base import ConnectorError
from app.models import Integration
from app.services.integrations import sync_integration
from app.services.notify import deliver_pending
from app.services.reminders import run_reminders

log = logging.getLogger("worker")
SYNC_EVERY = 6 * 60 * 60
REMIND_EVERY = 15 * 60
DELIVER_EVERY = 60


def sync_all() -> None:
    with system_session() as db:
        ids = [i.id for i in db.scalars(select(Integration).where(Integration.status != "disabled"))
               if not (i.config or {}).get("demo")]
    for integration_id in ids:
        with system_session() as db:
            integration = db.get(Integration, integration_id)
            try:
                results = sync_integration(db, integration)
                log.info("synced %s for org %s: %d checks", integration.provider, integration.org_id, len(results))
            except ConnectorError as e:
                log.warning("sync failed %s for org %s: %s", integration.provider, integration.org_id, e)


def reminders() -> None:
    with system_session() as db:
        run_reminders(db)


def deliver() -> None:
    with system_session() as db:
        n = deliver_pending(db)
        if n:
            log.info("processed %d notifications", n)


def ai_jobs() -> None:
    from app.services.ai import process_pending

    with system_session() as db:
        n = process_pending(db)
        if n:
            log.info("processed %d ai jobs", n)


def evidence_maintenance() -> None:
    """Fingerprint older file evidence and re-check evidence links weekly."""
    from app.models import Organization
    from app.services import evidence_checks

    with system_session() as db:
        for org in db.scalars(select(Organization)):
            evidence_checks.backfill_hashes(db, org.id)
            evidence_checks.recheck_links(db, org.id)
            db.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    jobs = [(sync_all, SYNC_EVERY), (reminders, REMIND_EVERY), (deliver, DELIVER_EVERY), (ai_jobs, 15),
            (evidence_maintenance, 60 * 60)]
    last = {fn: 0.0 for fn, _ in jobs}
    while True:
        for fn, every in jobs:
            if args.once or time.monotonic() - last[fn] >= every:
                try:
                    fn()
                except Exception:  # keep the worker alive; log and retry next cycle
                    log.exception("job %s failed", fn.__name__)
                last[fn] = time.monotonic()
        if args.once:
            return
        time.sleep(15)


if __name__ == "__main__":
    main()
