"""DPDP module: data inventory, data principal requests and incidents / breaches."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import DB, Ctx, WriterCtx, ensure_member, get_owned
from app.models import DataAsset, Incident, RightsRequest
from app.schemas import (
    DataAssetIn,
    DataAssetOut,
    IncidentIn,
    IncidentOut,
    IncidentUpdate,
    RightsRequestIn,
    RightsRequestOut,
    RightsRequestUpdate,
)
from app.services import audit

router = APIRouter()

CERTIN_HOURS = 6
DPB_DETAILED_HOURS = 72
GRIEVANCE_MAX_DAYS = 90  # DPDP Rules R.14: response within a period not exceeding 90 days


def _next_number(db, model, org_id) -> int:
    return (db.scalar(select(func.max(model.number)).where(model.org_id == org_id)) or 0) + 1


# ================================================================ data inventory


@router.get("/dpdp/assets", response_model=list[DataAssetOut], tags=["dpdp"])
def list_assets(db: DB, ctx: Ctx):
    return db.scalars(select(DataAsset).where(DataAsset.org_id == ctx.org_id).order_by(DataAsset.name)).all()


@router.post("/dpdp/assets", response_model=DataAssetOut, status_code=201, tags=["dpdp"])
def create_asset(body: DataAssetIn, db: DB, ctx: WriterCtx):
    ensure_member(db, ctx, body.owner_id)
    a = DataAsset(org_id=ctx.org_id, **body.model_dump())
    db.add(a)
    db.flush()
    audit.record(db, ctx, "data_asset.created", a, name=a.name)
    db.commit()
    db.refresh(a)
    return a


@router.put("/dpdp/assets/{asset_id}", response_model=DataAssetOut, tags=["dpdp"])
def update_asset(asset_id: uuid.UUID, body: DataAssetIn, db: DB, ctx: WriterCtx):
    a = get_owned(db, DataAsset, asset_id, ctx)
    ensure_member(db, ctx, body.owner_id)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    audit.record(db, ctx, "data_asset.updated", a)
    db.commit()
    db.refresh(a)
    return a


@router.delete("/dpdp/assets/{asset_id}", status_code=204, tags=["dpdp"])
def delete_asset(asset_id: uuid.UUID, db: DB, ctx: WriterCtx):
    a = get_owned(db, DataAsset, asset_id, ctx)
    audit.record(db, ctx, "data_asset.deleted", a, name=a.name)
    db.delete(a)
    db.commit()


# ================================================================ data principal requests


@router.get("/dpdp/requests", response_model=list[RightsRequestOut], tags=["dpdp"])
def list_requests(db: DB, ctx: Ctx):
    rows = db.scalars(select(RightsRequest).where(RightsRequest.org_id == ctx.org_id)).all()
    return sorted(rows, key=lambda r: (r.status in ("completed", "rejected"), r.due_at))


@router.post("/dpdp/requests", response_model=RightsRequestOut, status_code=201, tags=["dpdp"])
def create_request(body: RightsRequestIn, db: DB, ctx: WriterCtx):
    ensure_member(db, ctx, body.assignee_id)
    received = body.received_at or datetime.now(timezone.utc)
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    sla = min(ctx.org.rights_request_sla_days, GRIEVANCE_MAX_DAYS)
    r = RightsRequest(
        org_id=ctx.org_id, number=_next_number(db, RightsRequest, ctx.org_id),
        **body.model_dump(exclude={"received_at"}), received_at=received,
        due_at=received + timedelta(days=sla), legal_due_at=received + timedelta(days=GRIEVANCE_MAX_DAYS),
    )
    db.add(r)
    db.flush()
    audit.record(db, ctx, "rights_request.created", r, type=r.request_type)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/dpdp/requests/{request_id}", response_model=RightsRequestOut, tags=["dpdp"])
def update_request(request_id: uuid.UUID, body: RightsRequestUpdate, db: DB, ctx: WriterCtx):
    r = get_owned(db, RightsRequest, request_id, ctx)
    data = body.model_dump(exclude_unset=True)
    if "assignee_id" in data:
        ensure_member(db, ctx, data["assignee_id"])
    for k, v in data.items():
        setattr(r, k, v)
    if data.get("status") in ("completed", "rejected"):
        r.closed_at = r.closed_at or datetime.now(timezone.utc)
    elif "status" in data:
        r.closed_at = None
    audit.record(db, ctx, "rights_request.updated", r, fields=list(data))
    db.commit()
    db.refresh(r)
    return r


# ================================================================ incidents


def _apply_deadlines(i: Incident) -> None:
    i.certin_due_at = i.detected_at + timedelta(hours=CERTIN_HOURS) if i.certin_reportable else None
    i.dpb_due_at = i.detected_at + timedelta(hours=DPB_DETAILED_HOURS) if i.personal_data_breach else None


@router.get("/incidents", response_model=list[IncidentOut], tags=["incidents"])
def list_incidents(db: DB, ctx: Ctx):
    return db.scalars(
        select(Incident).where(Incident.org_id == ctx.org_id).order_by(Incident.detected_at.desc())
    ).all()


@router.post("/incidents", response_model=IncidentOut, status_code=201, tags=["incidents"])
def create_incident(body: IncidentIn, db: DB, ctx: WriterCtx):
    ensure_member(db, ctx, body.lead_id)
    i = Incident(org_id=ctx.org_id, number=_next_number(db, Incident, ctx.org_id), **body.model_dump())
    _apply_deadlines(i)
    db.add(i)
    db.flush()
    audit.record(db, ctx, "incident.created", i, severity=i.severity, certin=i.certin_reportable,
                 breach=i.personal_data_breach)
    db.commit()
    db.refresh(i)
    return i


@router.get("/incidents/{incident_id}", response_model=IncidentOut, tags=["incidents"])
def get_incident(incident_id: uuid.UUID, db: DB, ctx: Ctx):
    return get_owned(db, Incident, incident_id, ctx)


@router.patch("/incidents/{incident_id}", response_model=IncidentOut, tags=["incidents"])
def update_incident(incident_id: uuid.UUID, body: IncidentUpdate, db: DB, ctx: WriterCtx):
    i = get_owned(db, Incident, incident_id, ctx)
    data = body.model_dump(exclude_unset=True)
    if "lead_id" in data:
        ensure_member(db, ctx, data["lead_id"])
    for k, v in data.items():
        setattr(i, k, v)
    _apply_deadlines(i)
    if data.get("status") == "closed":
        i.closed_at = i.closed_at or datetime.now(timezone.utc)
    audit.record(db, ctx, "incident.updated", i, fields=list(data))
    db.commit()
    db.refresh(i)
    return i
