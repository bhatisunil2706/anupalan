"""Background worker: syncs every connected integration on a schedule.

Run with:  python -m app.worker            (loops forever)
           python -m app.worker --once     (single pass, e.g. from cron)
"""
import argparse
import logging
import time

from sqlalchemy import select

from app.db import SessionLocal
from app.integrations.base import ConnectorError
from app.models import Integration
from app.services.integrations import sync_integration

log = logging.getLogger("worker")
INTERVAL_SECONDS = 6 * 60 * 60


def run_once() -> None:
    with SessionLocal() as db:
        ids = list(db.scalars(select(Integration.id).where(Integration.status != "disabled")))
    for integration_id in ids:
        with SessionLocal() as db:
            integration = db.get(Integration, integration_id)
            try:
                results = sync_integration(db, integration)
                log.info("synced %s for org %s: %d checks", integration.provider, integration.org_id, len(results))
            except ConnectorError as e:
                log.warning("sync failed %s for org %s: %s", integration.provider, integration.org_id, e)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        run_once()
        if args.once:
            return
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
