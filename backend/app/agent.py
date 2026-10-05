"""Self-hosted personal data scanner agent.

Runs inside your network, connects read-only to a database or bucket, samples rows, and sends only categories,
counts and masked examples to Anupalan. Raw values never leave your network.

    docker run --rm --env-file scan.env anupalan/backend python -m app.agent

Environment:
    ANUPALAN_URL          e.g. https://app.anupalan.in
    ANUPALAN_API_KEY      an API key with the scanner:write scope
    SCAN_NAME             a name for this source, e.g. "orders-db (prod)"
    SCAN_KIND             postgres | mysql | s3
    SCAN_HOST, SCAN_PORT, SCAN_DATABASE, SCAN_USERNAME, SCAN_PASSWORD, SCAN_SSLMODE   (databases)
    SCAN_BUCKET, SCAN_PREFIX, SCAN_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY    (s3)
    SCAN_DRY_RUN=1        print the report instead of sending it
"""
import json
import os
import sys

import httpx

VERSION = "1.0"


def _env(name: str, required: bool = True, default: str = "") -> str:
    v = os.environ.get(name, default).strip()
    if required and not v:
        sys.exit(f"Missing environment variable {name}")
    return v


def build_report() -> dict:
    os.environ.setdefault("ALLOW_PRIVATE_SCAN_TARGETS", "true")  # the agent is meant to reach private hosts
    from app.services.scanner import SCANNERS

    kind = _env("SCAN_KIND")
    if kind not in SCANNERS:
        sys.exit(f"SCAN_KIND must be one of {', '.join(SCANNERS)}")
    if kind == "s3":
        cfg = {"bucket": _env("SCAN_BUCKET"), "prefix": _env("SCAN_PREFIX", False),
               "region": _env("SCAN_REGION", False, "ap-south-1")}
        secret = {"access_key_id": _env("AWS_ACCESS_KEY_ID", False), "secret_access_key":
                  _env("AWS_SECRET_ACCESS_KEY", False)}
    else:
        cfg = {"host": _env("SCAN_HOST"), "port": _env("SCAN_PORT", False), "database": _env("SCAN_DATABASE"),
               "username": _env("SCAN_USERNAME"), "sslmode": _env("SCAN_SSLMODE", False)}
        secret = {"password": _env("SCAN_PASSWORD", False)}
    findings, stats = SCANNERS[kind](cfg, secret)
    return {"source_name": _env("SCAN_NAME"), "source_kind": kind, "agent_version": VERSION,
            "stats": {k: v for k, v in stats.items() if isinstance(v, int)}, "findings": findings}


def main() -> None:
    report = build_report()
    if os.environ.get("SCAN_DRY_RUN") == "1":
        print(json.dumps(report, indent=2))
        return
    url = _env("ANUPALAN_URL").rstrip("/")
    if not url.startswith("https://") and not os.environ.get("ANUPALAN_ALLOW_HTTP"):
        sys.exit("ANUPALAN_URL must use https://")
    r = httpx.post(f"{url}/api/v1/scanner/findings", json=report, timeout=60,
                   headers={"Authorization": f"Bearer {_env('ANUPALAN_API_KEY')}"})
    if r.status_code != 200:
        sys.exit(f"Upload failed ({r.status_code}): {r.text[:300]}")
    print(f"Sent {len(report['findings'])} findings for {report['source_name']}")


if __name__ == "__main__":
    main()
