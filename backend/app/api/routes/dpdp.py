"""DPDP module: data inventory, data principal requests and incidents / breaches."""
import copy
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DB, Ctx, WriterCtx, ensure_member, get_owned
from app.models import DataAsset, Framework, Incident, IncidentEvent, OrgFramework, RightsRequest
from app.regulators import REGULATORS
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
from app.services import audit, incidents

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
    i = Incident(org_id=ctx.org_id, number=_next_number(db, Incident, ctx.org_id), reported_by_id=ctx.user.id,
                 **body.model_dump())
    _apply_deadlines(i)
    db.add(i)
    db.flush()
    i.follower_ids = incidents.initial_followers(db, i)
    audit.record(db, ctx, "incident.created", i, severity=i.severity, certin=i.certin_reportable,
                 breach=i.personal_data_breach)
    incidents.reported(db, i, ctx.user)
    db.commit()
    db.refresh(i)
    return i


@router.get("/incident-regulators", tags=["incidents"])
def incident_regulators(db: DB, ctx: Ctx):
    """Sector regulators an incident can be reported to, with the ones suggested by the organisation's frameworks."""
    enabled = set(db.scalars(select(Framework.code).join(OrgFramework, OrgFramework.framework_id == Framework.id)
                             .where(OrgFramework.org_id == ctx.org_id)))
    return [{"key": r.key, "label": r.name, "hint": r.hint, "suggested": bool(r.frameworks & enabled)}
            for r in REGULATORS.values()]


@router.get("/incidents/{incident_id}", response_model=IncidentOut, tags=["incidents"])
def get_incident(incident_id: uuid.UUID, db: DB, ctx: Ctx):
    return get_owned(db, Incident, incident_id, ctx)


@router.patch("/incidents/{incident_id}", response_model=IncidentOut, tags=["incidents"])
def update_incident(incident_id: uuid.UUID, body: IncidentUpdate, db: DB, ctx: WriterCtx):
    i = get_owned(db, Incident, incident_id, ctx)
    data = body.model_dump(exclude_unset=True)
    if "lead_id" in data:
        ensure_member(db, ctx, data["lead_id"])
    before = {k: copy.deepcopy(getattr(i, k)) for k in data}
    reported = data.pop("regulator_reported", None)
    if reported is not None:
        merged = dict(i.regulator_reported or {})
        for key, at in reported.items():
            if at is None:
                merged.pop(key, None)
            else:
                merged[key] = at.isoformat()
        i.regulator_reported = merged
        data["regulator_reported"] = reported
    for k, v in data.items():
        if k != "regulator_reported":
            setattr(i, k, v)
    _apply_deadlines(i)
    if data.get("status") == "closed":
        i.closed_at = i.closed_at or datetime.now(timezone.utc)
    elif "status" in data and i.status != "closed":
        i.closed_at = None
    db.flush()
    db.expire(i, ["lead"])
    incidents.changes(db, i, ctx.user, before, data)
    audit.record(db, ctx, "incident.updated", i, fields=list(data))
    db.commit()
    db.refresh(i)
    return i


class IncidentNoteIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


def _event_out(e: IncidentEvent) -> dict:
    return {"id": e.id, "kind": e.kind, "message": e.message, "created_at": e.created_at,
            "user": {"id": e.user.id, "full_name": e.user.full_name, "email": e.user.email} if e.user else None}


@router.get("/incidents/{incident_id}/activity", tags=["incidents"])
def incident_activity(incident_id: uuid.UUID, db: DB, ctx: Ctx):
    """The timeline and who receives email updates."""
    i = get_owned(db, Incident, incident_id, ctx)
    events = db.scalars(select(IncidentEvent).where(IncidentEvent.incident_id == i.id)
                        .options(selectinload(IncidentEvent.user)).order_by(IncidentEvent.created_at.desc())).all()
    people = incidents.followers(db, i)
    return {"events": [_event_out(e) for e in events],
            "followers": [{"id": u.id, "full_name": u.full_name, "email": u.email} for u in people],
            "following": any(u.id == ctx.user.id for u in people),
            "reported_by": ({"id": i.reported_by.id, "full_name": i.reported_by.full_name,
                             "email": i.reported_by.email} if i.reported_by else None)}


@router.post("/incidents/{incident_id}/updates", status_code=201, tags=["incidents"])
def post_incident_update(incident_id: uuid.UUID, body: IncidentNoteIn, db: DB, ctx: WriterCtx):
    """Post an update to the timeline; it is emailed to everyone following the incident."""
    i = get_owned(db, Incident, incident_id, ctx)
    ev = incidents.record(db, i, ctx.user, "note", body.message.strip())
    audit.record(db, ctx, "incident.update_posted", i)
    db.commit()
    db.refresh(ev)
    return _event_out(ev)


@router.post("/incidents/{incident_id}/follow", tags=["incidents"])
def follow_incident(incident_id: uuid.UUID, db: DB, ctx: Ctx):
    i = get_owned(db, Incident, incident_id, ctx)
    incidents.follow(i, ctx.user.id)
    audit.record(db, ctx, "incident.followed", i)
    db.commit()
    return {"following": True}


@router.delete("/incidents/{incident_id}/follow", tags=["incidents"])
def unfollow_incident(incident_id: uuid.UUID, db: DB, ctx: Ctx):
    i = get_owned(db, Incident, incident_id, ctx)
    incidents.unfollow(i, ctx.user.id)
    audit.record(db, ctx, "incident.unfollowed", i)
    db.commit()
    return {"following": False}
