"""Admin commands.

python -m app.cli load-content     Load / refresh frameworks, controls, mappings and policy templates
python -m app.cli check-content    Validate content mapping coverage without touching the database
python -m app.cli seed-demo [--reset] [--password PW]   Create 3 demo companies (refuses in production)
python -m app.cli remove-demo      Delete the demo companies and users
python -m app.cli verify-audit     Verify every organisation's audit hash chain
"""
import argparse
import sys

from app.db import system_session
from app.services.content import load_content, read_controls, read_frameworks, validate_content


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "load-content":
        with system_session() as db:
            print(load_content(db))
    elif cmd == "check-content":
        validate_content(read_frameworks(), read_controls())
        print("Content OK: every requirement maps to at least one control.")
    elif cmd in ("seed-demo", "remove-demo"):
        from app.config import get_settings
        from app.services import demo

        if get_settings().is_production:
            sys.exit("Refusing to touch demo data in production.")
        parser = argparse.ArgumentParser(prog=f"app.cli {cmd}")
        parser.add_argument("--reset", action="store_true")
        parser.add_argument("--password", default=demo.DEFAULT_PASSWORD)
        args = parser.parse_args(sys.argv[2:])
        with system_session() as db:
            if cmd == "remove-demo":
                demo.remove_demo(db)
                print("Demo data removed.")
                return
            result = demo.seed(db, password=args.password, reset=args.reset)
        print(f"Demo data created. Password for every login: {args.password}\n")
        for org in result:
            print(org["org"])
            for login in org["logins"]:
                print(f"  {login['role']:<8} {login['email']:<36} {login['name']}")
    elif cmd == "verify-audit":
        from sqlalchemy import select

        from app.models import Organization
        from app.services.audit import verify_chain

        bad = 0
        with system_session() as db:
            for org in db.scalars(select(Organization)):
                r = verify_chain(db, org.id)
                bad += not r["ok"]
                print(f"{'OK  ' if r['ok'] else 'FAIL'} {org.name}: {r['entries']} entries"
                      + ("" if r["ok"] else f", broken at #{r['broken_at']}"))
        sys.exit(1 if bad else 0)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
