"""DPDP consent records: versioned notices, an append-only consent log, and a machine API for websites and apps."""
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.deps import DB, AdminCtx, ApiKeyContext, Ctx, WriterCtx, api_key_auth
from app.models import ConsentEvent, ConsentNotice
from app.services import audit

router = APIRouter(tags=["consent"])


# ================================================================ notices


class Purpose(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    required: bool = False


class NoticeIn(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_-]{2,60}$")
    title: str = Field(min_length=1, max_length=200)
    body_md: str = Field(default="", max_length=50000)
    purposes: list[Purpose] = Field(min_length=1, max_length=30)
    languages: list[str] = Field(default_factory=lambda: ["en"])

    @field_validator("purposes")
    @classmethod
    def unique_ids(cls, v):
        if len({p.id for p in v}) != len(v):
            raise ValueError("purpose ids must be unique")
        return v


def _notice_out(n: ConsentNotice) -> dict:
    return {"id": n.id, "key": n.key, "version": n.version, "title": n.title, "body_md": n.body_md,
            "purposes": n.purposes, "languages": n.languages, "status": n.status, "published_at": n.published_at,
            "updated_at": n.updated_at}


@router.get("/consent/notices")
def list_notices(db: DB, ctx: Ctx):
    rows = db.scalars(select(ConsentNotice).where(ConsentNotice.org_id == ctx.org_id)
                      .order_by(ConsentNotice.key, ConsentNotice.version.desc()))
    return [_notice_out(n) for n in rows]


@router.post("/consent/notices", status_code=201)
def create_notice(body: NoticeIn, db: DB, ctx: WriterCtx):
    """Create a draft. If the key already exists this becomes its next version."""
    if db.scalar(select(ConsentNotice.id).where(ConsentNotice.org_id == ctx.org_id, ConsentNotice.key == body.key,
                                                ConsentNotice.status == "draft")):
        raise HTTPException(status.HTTP_409_CONFLICT, "There's already a draft for this notice. Edit or publish it.")
    latest = db.scalar(select(func.max(ConsentNotice.version)).where(ConsentNotice.org_id == ctx.org_id,
                                                                    ConsentNotice.key == body.key)) or 0
    n = ConsentNotice(org_id=ctx.org_id, key=body.key, version=latest + 1, title=body.title, body_md=body.body_md,
                      purposes=[p.model_dump() for p in body.purposes], languages=body.languages)
    db.add(n)
    db.flush()
    audit.record(db, ctx, "consent.notice_created", n, key=n.key, version=n.version)
    db.commit()
    return _notice_out(n)


@router.put("/consent/notices/{notice_id}")
def update_notice(notice_id: uuid.UUID, body: NoticeIn, db: DB, ctx: WriterCtx):
    n = db.get(ConsentNotice, notice_id)
    if not n or n.org_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notice not found")
    if n.status != "draft":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Published notices can't change, because consent was given against them. Create a new "
                            "version instead.")
    n.title, n.body_md, n.languages = body.title, body.body_md, body.languages
    n.purposes = [p.model_dump() for p in body.purposes]
    db.commit()
    return _notice_out(n)


@router.post("/consent/notices/{notice_id}/publish")
def publish_notice(notice_id: uuid.UUID, db: DB, ctx: AdminCtx):
    n = db.get(ConsentNotice, notice_id)
    if not n or n.org_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notice not found")
    if n.status != "draft":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only drafts can be published")
    for old in db.scalars(select(ConsentNotice).where(ConsentNotice.org_id == ctx.org_id,
                                                      ConsentNotice.key == n.key, ConsentNotice.status == "published")):
        old.status = "retired"
    n.status, n.published_at = "published", datetime.now(timezone.utc)
    audit.record(db, ctx, "consent.notice_published", n, key=n.key, version=n.version)
    db.commit()
    return _notice_out(n)


# ================================================================ recording consent


class ConsentEventIn(BaseModel):
    event_id: str = Field(min_length=1, max_length=100, description="Your unique ID for this event (idempotency)")
    principal_id: str = Field(min_length=1, max_length=200, description="Your identifier for the person")
    notice_key: str = Field(max_length=60)
    notice_version: int | None = Field(default=None, description="Defaults to the currently published version")
    action: Literal["granted", "withdrawn"]
    purposes: list[str] = Field(default_factory=list, max_length=30,
                                description="Purpose ids. For withdrawn, empty means all purposes.")
    source: Literal["web", "app", "api", "import", "consent_manager", "call_centre", "paper"] = "api"
    language: str = Field(default="en", max_length=10)
    occurred_at: datetime | None = None
    consent_manager_ref: str = Field(default="", max_length=200)
    metadata: dict = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def small_metadata(cls, v):
        if len(str(v)) > 4000:
            raise ValueError("metadata is too large (max ~4 KB)")
        return v


def _record(db, org_id: uuid.UUID, body: ConsentEventIn) -> tuple[ConsentEvent, bool]:
    now = datetime.now(timezone.utc)
    occurred = body.occurred_at or now
    if occurred.tzinfo is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "occurred_at must include a timezone offset")
    if occurred > now + timedelta(minutes=5):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "occurred_at can't be in the future")
    q = select(ConsentNotice).where(ConsentNotice.org_id == org_id, ConsentNotice.key == body.notice_key,
                                    ConsentNotice.status.in_(("published", "retired")))
    q = q.where(ConsentNotice.version == body.notice_version) if body.notice_version else q.where(
        ConsentNotice.status == "published")
    notice = db.scalar(q)
    if not notice:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown or unpublished notice key/version")
    valid = {p["id"] for p in notice.purposes}
    unknown = set(body.purposes) - valid
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown purposes: {sorted(unknown)}")
    if body.action == "granted":
        if not body.purposes:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "List the purposes consented to")
        missing = {p["id"] for p in notice.purposes if p.get("required")} - set(body.purposes)
        if missing:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Required purposes missing: {sorted(missing)}")
    values = dict(id=uuid.uuid4(), org_id=org_id, event_id=body.event_id, principal_id=body.principal_id,
                  notice_key=notice.key, notice_version=notice.version, action=body.action,
                  purposes=sorted(set(body.purposes)), source=body.source, language=body.language,
                  consent_manager_ref=body.consent_manager_ref, metadata_=body.metadata, occurred_at=occurred,
                  received_at=now)
    stmt = insert(ConsentEvent).values(**{("metadata" if k == "metadata_" else k): v for k, v in values.items()})
    inserted = db.scalar(stmt.on_conflict_do_nothing(index_elements=["org_id", "event_id"])
                         .returning(ConsentEvent.id))
    created = inserted is not None
    ev = db.scalar(select(ConsentEvent).where(ConsentEvent.org_id == org_id, ConsentEvent.event_id == body.event_id))
    return ev, created


def principal_state(db, org_id: uuid.UUID, principal_id: str) -> dict:
    state: dict[str, dict] = {}
    for e in db.scalars(select(ConsentEvent).where(ConsentEvent.org_id == org_id,
                                                   ConsentEvent.principal_id == principal_id)
                        .order_by(ConsentEvent.occurred_at, ConsentEvent.received_at)):
        s = state.setdefault(e.notice_key, {"version": e.notice_version, "purposes": set(), "updated_at": None})
        if e.action == "granted":
            s["purposes"] = set(e.purposes)
            s["version"] = e.notice_version
        else:
            s["purposes"] = set() if not e.purposes else s["purposes"] - set(e.purposes)
        s["updated_at"] = e.occurred_at
    return {k: {"version": v["version"], "purposes": sorted(v["purposes"]), "updated_at": v["updated_at"]}
            for k, v in state.items()}


def _event_out(e: ConsentEvent) -> dict:
    return {"id": e.id, "event_id": e.event_id, "principal_id": e.principal_id, "notice_key": e.notice_key,
            "notice_version": e.notice_version, "action": e.action, "purposes": e.purposes, "source": e.source,
            "language": e.language, "consent_manager_ref": e.consent_manager_ref, "metadata": e.metadata_,
            "occurred_at": e.occurred_at, "received_at": e.received_at}


# ---------------------------------------------------------------- machine API (API key)

ConsentWriter = Annotated[ApiKeyContext, Depends(api_key_auth("consent:write"))]
ConsentReader = Annotated[ApiKeyContext, Depends(api_key_auth("consent:read"))]


@router.post("/v1/consent/events", status_code=201)
def api_record_event(body: ConsentEventIn, db: DB, key: ConsentWriter, response: Response):
    ev, created = _record(db, key.org_id, body)
    db.commit()
    if not created:
        response.status_code = status.HTTP_200_OK  # idempotent replay of the same event_id
    return _event_out(ev)


@router.get("/v1/consent/principals/{principal_id}")
def api_principal(principal_id: str, db: DB, key: ConsentReader):
    return {"principal_id": principal_id, "consents": principal_state(db, key.org_id, principal_id)}


@router.get("/v1/consent/events")
def api_events(db: DB, key: ConsentReader, since: datetime | None = None,
               action: Literal["granted", "withdrawn"] | None = None, limit: int = 500):
    """Poll for changes, e.g. withdrawals your downstream systems must act on (DPDP s.6(6))."""
    q = select(ConsentEvent).where(ConsentEvent.org_id == key.org_id)
    if since:
        q = q.where(ConsentEvent.received_at > since)
    if action:
        q = q.where(ConsentEvent.action == action)
    rows = db.scalars(q.order_by(ConsentEvent.received_at).limit(max(1, min(limit, 1000)))).all()
    return {"events": [_event_out(e) for e in rows], "next_since": rows[-1].received_at if rows else since}


# ---------------------------------------------------------------- in-app views


@router.post("/consent/events", status_code=201)
def record_event_manually(body: ConsentEventIn, db: DB, ctx: WriterCtx):
    """Record consent captured offline (paper form, call centre)."""
    ev, created = _record(db, ctx.org_id, body)
    if created:
        audit.record(db, ctx, "consent.recorded_manually", None, principal=body.principal_id,
                     consent_action=body.action)
    db.commit()
    return _event_out(ev)


@router.get("/consent/events")
def list_events(db: DB, ctx: Ctx, principal_id: str | None = None, limit: int = 200):
    q = select(ConsentEvent).where(ConsentEvent.org_id == ctx.org_id)
    if principal_id:
        q = q.where(ConsentEvent.principal_id == principal_id)
    return [_event_out(e) for e in db.scalars(q.order_by(ConsentEvent.received_at.desc()).limit(min(limit, 1000)))]


@router.get("/consent/principals/{principal_id}")
def principal(principal_id: str, db: DB, ctx: Ctx):
    return {"principal_id": principal_id, "consents": principal_state(db, ctx.org_id, principal_id)}


@router.get("/consent/summary")
def summary(db: DB, ctx: Ctx):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    counts = dict(db.execute(select(ConsentEvent.action, func.count()).where(
        ConsentEvent.org_id == ctx.org_id, ConsentEvent.received_at >= since).group_by(ConsentEvent.action)).all())
    principals = db.scalar(select(func.count(func.distinct(ConsentEvent.principal_id))).where(
        ConsentEvent.org_id == ctx.org_id))
    by_source = dict(db.execute(select(ConsentEvent.source, func.count()).where(
        ConsentEvent.org_id == ctx.org_id, ConsentEvent.received_at >= since).group_by(ConsentEvent.source)).all())
    last = db.scalar(select(func.max(ConsentEvent.received_at)).where(ConsentEvent.org_id == ctx.org_id))
    return {"granted_30d": counts.get("granted", 0), "withdrawn_30d": counts.get("withdrawn", 0),
            "principals": principals or 0, "by_source_30d": by_source, "last_event_at": last}


@router.get("/consent/export")
def export_events(db: DB, ctx: Ctx):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["received_at_utc", "occurred_at_utc", "principal_id", "notice_key", "notice_version", "action",
                "purposes", "source", "language", "event_id"])
    for e in db.scalars(select(ConsentEvent).where(ConsentEvent.org_id == ctx.org_id)
                        .order_by(ConsentEvent.received_at)):
        w.writerow([e.received_at.isoformat(), e.occurred_at.isoformat(), e.principal_id, e.notice_key,
                    e.notice_version, e.action, " ".join(e.purposes), e.source, e.language, e.event_id])
    audit.record(db, ctx, "consent.exported")
    db.commit()
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="consent-log.csv"'})
