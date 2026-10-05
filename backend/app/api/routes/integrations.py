from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DB, AdminCtx, Ctx
from app.integrations import REGISTRY
from app.integrations.base import ConnectorError
from app.models import Integration, TestResult
from app.schemas import IntegrationConnectIn
from app.security import encrypt_json
from app.services import audit
from app.services.integrations import sync_integration

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _out(i: Integration | None) -> dict | None:
    if i is None:
        return None
    return {"id": i.id, "status": i.status, "config": i.config, "last_synced_at": i.last_synced_at,
            "last_error": i.last_error, "connected_at": i.created_at}


@router.get("")
def list_integrations(db: DB, ctx: Ctx):
    connected = {i.provider: i for i in db.scalars(select(Integration).where(Integration.org_id == ctx.org_id))}
    return [{**cls.describe(), "connection": _out(connected.get(p))} for p, cls in REGISTRY.items()]


def _connector_cls(provider: str):
    cls = REGISTRY.get(provider)
    if not cls:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown integration")
    return cls


@router.post("/{provider}")
def connect(provider: str, body: IntegrationConnectIn, db: DB, ctx: AdminCtx):
    cls = _connector_cls(provider)
    config, secrets = {}, {}
    for f in cls.fields:
        value = (body.secrets if f.secret else body.config).get(f.name, "").strip() or f.default
        if f.required and not value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{f.label} is required")
        (secrets if f.secret else config)[f.name] = value
    try:
        cls(config, secrets).verify()
    except ConnectorError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    i = db.scalar(select(Integration).where(Integration.org_id == ctx.org_id, Integration.provider == provider))
    i = i or Integration(org_id=ctx.org_id, provider=provider)
    i.config, i.secret_encrypted, i.status, i.last_error = config, encrypt_json(secrets), "connected", ""
    db.add(i)
    db.flush()
    audit.record(db, ctx, "integration.connected", i, provider=provider)
    db.commit()
    return _out(i)


def _get(db, ctx, provider: str) -> Integration:
    i = db.scalar(select(Integration).where(Integration.org_id == ctx.org_id, Integration.provider == provider))
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration not connected")
    return i


@router.post("/{provider}/sync")
def sync(provider: str, db: DB, ctx: AdminCtx):
    i = _get(db, ctx, provider)
    try:
        results = sync_integration(db, i)
    except ConnectorError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    audit.record(db, ctx, "integration.synced", i, provider=provider,
                 passed=sum(r.status == "pass" for r in results), failed=sum(r.status == "fail" for r in results))
    db.commit()
    return {"results": [r.__dict__ for r in results], "connection": _out(i)}


@router.get("/{provider}/results")
def results(provider: str, db: DB, ctx: Ctx):
    i = _get(db, ctx, provider)
    rows = db.scalars(select(TestResult).where(TestResult.integration_id == i.id).order_by(TestResult.run_at.desc())
                      .limit(200))
    latest = {}
    for r in rows:
        latest.setdefault(r.test_key, r)
    return [{"key": r.test_key, "title": r.title, "status": r.status, "run_at": r.run_at,
             "control_codes": r.control_codes, "details": r.details} for r in latest.values()]


@router.delete("/{provider}", status_code=204)
def disconnect(provider: str, db: DB, ctx: AdminCtx):
    i = _get(db, ctx, provider)
    audit.record(db, ctx, "integration.disconnected", i, provider=provider)
    db.delete(i)
    db.commit()
