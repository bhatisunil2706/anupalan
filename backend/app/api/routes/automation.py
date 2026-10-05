"""People & accounts, access reviews, notification settings and personal data discovery."""
import uuid
from datetime import date

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.deps import DB, AdminCtx, Ctx, WriterCtx, ensure_member, get_owned
from app.integrations import REGISTRY
from app.models import AccessReview, AccessReviewItem, Account, DataAsset, DataSource, Person, PiiFinding
from app.security import encrypt_json
from app.services import audit, notify
from app.services.access_reviews import complete, create_review, decide, export_csv, system_name
from app.services.people import RosterError, parse_csv, upsert_people
from app.services.pii import LABELS, SENSITIVE
from app.services.platform_checks import leaver_findings, run_platform_checks
from app.services.scanner import REQUIRED, ScanError, scan_source

router = APIRouter()

# ================================================================ people & accounts


@router.get("/people", tags=["people"])
def list_people(db: DB, ctx: Ctx):
    people = db.scalars(select(Person).where(Person.org_id == ctx.org_id).order_by(Person.status, Person.full_name))
    accounts: dict[str, list[dict]] = {}
    for a in db.scalars(select(Account).where(Account.org_id == ctx.org_id, Account.email != "")):
        accounts.setdefault(a.email, []).append({"system": system_name(a.provider), "active": a.is_active,
                                                 "admin": a.is_admin, "mfa": a.mfa_enabled})
    return [
        {"id": p.id, "email": p.email, "full_name": p.full_name, "employee_id": p.employee_id,
         "department": p.department, "title": p.title, "manager_email": p.manager_email, "status": p.status,
         "join_date": p.join_date, "exit_date": p.exit_date, "source": p.source,
         "accounts": accounts.get(p.email, [])}
        for p in people
    ]


@router.post("/people/upload", tags=["people"])
async def upload_people(db: DB, ctx: AdminCtx, file: UploadFile = File(...)):
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 5 MB)")
    try:
        records, warnings = parse_csv(content)
    except RosterError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    result = upsert_people(db, ctx.org_id, records, source="csv")
    run_platform_checks(db, ctx.org)
    audit.record(db, ctx, "people.imported", None, **result)
    db.commit()
    return {**result, "warnings": warnings,
            "exited": sum(1 for r in records if r.status == "exited")}


@router.delete("/people", status_code=204, tags=["people"])
def clear_people(db: DB, ctx: AdminCtx):
    db.execute(delete(Person).where(Person.org_id == ctx.org_id))
    audit.record(db, ctx, "people.cleared")
    db.commit()


@router.get("/accounts", tags=["people"])
def list_accounts(db: DB, ctx: Ctx):
    people = {p.email: p for p in db.scalars(select(Person).where(Person.org_id == ctx.org_id))}
    rows = db.scalars(select(Account).where(Account.org_id == ctx.org_id).order_by(Account.provider, Account.email))
    return [
        {"id": a.id, "system": system_name(a.provider), "provider": a.provider, "email": a.email, "name": a.name,
         "is_admin": a.is_admin, "is_active": a.is_active, "mfa_enabled": a.mfa_enabled,
         "last_login_at": a.last_login_at, "synced_at": a.synced_at,
         "person_status": people[a.email].status if a.email in people else ("unknown" if a.email else "unmatched")}
        for a in rows
    ]


@router.get("/people/leavers-with-access", tags=["people"])
def leavers_with_access(db: DB, ctx: Ctx):
    findings, leavers, accounts = leaver_findings(db, ctx.org_id)
    return {"findings": findings, "leavers_checked": leavers, "accounts_checked": accounts}


# ================================================================ access reviews


class ReviewIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    providers: list[str] = Field(min_length=1)
    due_date: date | None = None
    default_reviewer_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(keep|revoke|pending)$")
    note: str = ""


def _review_summary(r: AccessReview, user_id) -> dict:
    items = r.items
    return {
        "id": r.id, "title": r.title, "status": r.status, "due_date": r.due_date,
        "providers": [{"provider": p, "name": system_name(p)} for p in r.providers],
        "created_by": r.created_by.full_name if r.created_by else None, "created_at": r.created_at,
        "completed_at": r.completed_at, "total": len(items),
        "pending": sum(i.decision == "pending" for i in items),
        "revoked": sum(i.decision == "revoke" for i in items),
        "kept": sum(i.decision == "keep" for i in items),
        "my_pending": sum(i.decision == "pending" and i.reviewer_id == user_id for i in items),
        "removals_unverified": sum(i.decision == "revoke" and not i.removal_verified_at for i in items),
    }


@router.get("/access-reviews", tags=["access reviews"])
def list_reviews(db: DB, ctx: Ctx):
    rows = db.scalars(select(AccessReview).where(AccessReview.org_id == ctx.org_id)
                      .options(selectinload(AccessReview.items)).order_by(AccessReview.created_at.desc()))
    systems = sorted({p for p in db.scalars(select(Account.provider).where(Account.org_id == ctx.org_id))})
    counts = dict(db.execute(select(Account.provider, func.count()).where(
        Account.org_id == ctx.org_id, Account.is_active.is_(True)).group_by(Account.provider)).all())
    return {
        "reviews": [_review_summary(r, ctx.user.id) for r in rows],
        "available_systems": [{"provider": p, "name": system_name(p), "accounts": counts.get(p, 0)} for p in systems],
    }


@router.post("/access-reviews", status_code=201, tags=["access reviews"])
def start_review(body: ReviewIn, db: DB, ctx: AdminCtx):
    unknown = [p for p in body.providers if p not in REGISTRY]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown systems: {unknown}")
    ensure_member(db, ctx, body.default_reviewer_id)
    review = create_review(db, ctx, body.title, body.providers, body.due_date, body.default_reviewer_id)
    audit.record(db, ctx, "access_review.started", review, items=len(review.items))
    db.commit()
    return {"id": review.id}


def _get_review(db, ctx, review_id) -> AccessReview:
    r = get_owned(db, AccessReview, review_id, ctx)
    db.refresh(r, attribute_names=["items"])
    return r


@router.get("/access-reviews/{review_id}", tags=["access reviews"])
def review_detail(review_id: uuid.UUID, db: DB, ctx: Ctx):
    r = _get_review(db, ctx, review_id)
    items = sorted(r.items, key=lambda i: (i.decision != "pending", i.reviewer_id != ctx.user.id,
                                           i.person_status != "exited", i.provider, i.email or i.name))
    return {
        **_review_summary(r, ctx.user.id),
        "items": [
            {"id": i.id, "system": system_name(i.provider), "email": i.email, "name": i.name, "is_admin": i.is_admin,
             "person_status": i.person_status, "reviewer": i.reviewer.full_name if i.reviewer else None,
             "reviewer_id": i.reviewer_id, "decision": i.decision, "note": i.note,
             "decided_by": i.decided_by.full_name if i.decided_by else None, "decided_at": i.decided_at,
             "removal_verified_at": i.removal_verified_at,
             "can_decide": r.status == "open" and (i.reviewer_id == ctx.user.id or ctx.is_admin)}
            for i in items
        ],
    }


@router.patch("/access-reviews/{review_id}/items/{item_id}", tags=["access reviews"])
def decide_item(review_id: uuid.UUID, item_id: uuid.UUID, body: DecisionIn, db: DB, ctx: WriterCtx):
    item = db.get(AccessReviewItem, item_id)
    if not item or item.org_id != ctx.org_id or item.review_id != review_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    decide(db, ctx, item, body.decision, body.note)
    db.commit()
    return {"decision": item.decision, "removal_verified_at": item.removal_verified_at}


@router.post("/access-reviews/{review_id}/complete", tags=["access reviews"])
def complete_review(review_id: uuid.UUID, db: DB, ctx: AdminCtx):
    r = _get_review(db, ctx, review_id)
    ev = complete(db, ctx, r)
    audit.record(db, ctx, "access_review.completed", r)
    db.commit()
    return {"status": r.status, "evidence_id": ev.id if ev else None}


@router.get("/access-reviews/{review_id}/export", tags=["access reviews"])
def export_review(review_id: uuid.UUID, db: DB, ctx: Ctx):
    r = _get_review(db, ctx, review_id)
    return Response(export_csv(db, r), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="access-review-{r.id}.csv"'})


# ================================================================ notification settings


class NotificationSettingsIn(BaseModel):
    notify_email: bool | None = None
    slack_webhook_url: str | None = None
    teams_webhook_url: str | None = None


@router.get("/org/notifications", tags=["notifications"])
def notification_settings(ctx: AdminCtx):
    hooks = notify.get_webhooks(ctx.org)
    return {"notify_email": ctx.org.notify_email, "slack_configured": bool(hooks.get("slack")),
            "teams_configured": bool(hooks.get("teams"))}


@router.put("/org/notifications", tags=["notifications"])
def update_notifications(body: NotificationSettingsIn, db: DB, ctx: AdminCtx):
    if body.notify_email is not None:
        ctx.org.notify_email = body.notify_email
    try:
        notify.set_webhooks(ctx.org, body.slack_webhook_url, body.teams_webhook_url)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    audit.record(db, ctx, "notifications.updated", ctx.org)
    db.commit()
    return notification_settings(ctx)


@router.post("/org/notifications/test", tags=["notifications"])
def test_notification(db: DB, ctx: AdminCtx):
    hooks = notify.get_webhooks(ctx.org)
    results = {}
    for kind, fn in (("slack", notify.post_slack), ("teams", notify.post_teams)):
        if hooks.get(kind):
            try:
                fn(hooks[kind], "Test notification", f"Alerts from {ctx.org.name} will appear here.", "")
                results[kind] = "sent"
            except Exception as e:  # noqa: BLE001
                results[kind] = f"failed: {e}"
    try:
        notify.send_email([ctx.user.email], f"[{ctx.org.name}] Test notification",
                          "Email notifications are working.")
        results["email"] = "sent"
    except Exception as e:  # noqa: BLE001
        results["email"] = f"failed: {e}"
    return results


# ================================================================ personal data discovery


class DataSourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(postgres|mysql|s3)$")
    config: dict[str, str] = {}
    secrets: dict[str, str] = {}


def _source_out(s: DataSource) -> dict:
    return {"id": s.id, "name": s.name, "kind": s.kind, "config": s.config, "status": s.status,
            "last_scan_at": s.last_scan_at, "last_error": s.last_error, "stats": s.stats}


@router.get("/discovery/sources", tags=["discovery"])
def list_sources(db: DB, ctx: Ctx):
    return [_source_out(s) for s in db.scalars(select(DataSource).where(DataSource.org_id == ctx.org_id)
                                                .order_by(DataSource.created_at))]


@router.post("/discovery/sources", status_code=201, tags=["discovery"])
def add_source(body: DataSourceIn, db: DB, ctx: AdminCtx):
    missing = [f for f in REQUIRED[body.kind] if not body.config.get(f, "").strip()]
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Missing: {', '.join(missing)}")
    s = DataSource(org_id=ctx.org_id, name=body.name, kind=body.kind,
                   config={k: v.strip() for k, v in body.config.items()}, secret_encrypted=encrypt_json(body.secrets))
    db.add(s)
    db.flush()
    audit.record(db, ctx, "data_source.added", s, kind=s.kind)
    db.commit()
    return _source_out(s)


@router.delete("/discovery/sources/{source_id}", status_code=204, tags=["discovery"])
def remove_source(source_id: uuid.UUID, db: DB, ctx: AdminCtx):
    s = get_owned(db, DataSource, source_id, ctx)
    audit.record(db, ctx, "data_source.removed", s)
    db.delete(s)
    db.commit()


@router.post("/discovery/sources/{source_id}/scan", tags=["discovery"])
def scan(source_id: uuid.UUID, db: DB, ctx: AdminCtx):
    s = get_owned(db, DataSource, source_id, ctx)
    if s.kind == "agent":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This source is scanned by your self-hosted agent")
    try:
        n = scan_source(db, s)
    except ScanError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    audit.record(db, ctx, "data_source.scanned", s, findings=n)
    db.commit()
    return _source_out(s)


@router.get("/discovery/findings", tags=["discovery"])
def findings(db: DB, ctx: Ctx):
    sources = {s.id: s for s in db.scalars(select(DataSource).where(DataSource.org_id == ctx.org_id))}
    grouped: dict[tuple, dict] = {}
    for f in db.scalars(select(PiiFinding).where(PiiFinding.org_id == ctx.org_id)
                        .order_by(PiiFinding.container, PiiFinding.field)):
        key = (f.source_id, f.container)
        g = grouped.setdefault(key, {"source_id": f.source_id, "source": sources[f.source_id].name,
                                     "container": f.container, "fields": [], "categories": set()})
        g["fields"].append({"field": f.field, "category": f.category, "label": LABELS.get(f.category, f.category),
                            "matches": f.matches, "sampled": f.sampled, "by_name_only": f.by_name_only,
                            "examples": f.examples, "sensitive": f.category in SENSITIVE})
        g["categories"].add(f.category)
    out = []
    for g in grouped.values():
        cats = g.pop("categories")
        g["categories"] = sorted(LABELS.get(c, c) for c in cats)
        g["sensitive"] = bool(cats & SENSITIVE)
        out.append(g)
    return sorted(out, key=lambda g: (not g["sensitive"], -len(g["categories"]), g["container"]))


class ToInventoryIn(BaseModel):
    source_id: uuid.UUID
    container: str
    name: str = Field(min_length=1, max_length=200)
    purposes: str = ""


@router.post("/discovery/to-inventory", status_code=201, tags=["discovery"])
def add_to_inventory(body: ToInventoryIn, db: DB, ctx: WriterCtx):
    s = get_owned(db, DataSource, body.source_id, ctx)
    cats = sorted({LABELS.get(f.category, f.category) for f in db.scalars(select(PiiFinding).where(
        PiiFinding.source_id == s.id, PiiFinding.container == body.container))})
    if not cats:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No findings for that location")
    asset = DataAsset(org_id=ctx.org_id, name=body.name, purposes=body.purposes, data_categories=cats,
                      systems=[f"{s.name}: {body.container}"],
                      description=f"Added from personal data discovery ({s.kind}).")
    db.add(asset)
    db.flush()
    audit.record(db, ctx, "data_asset.created", asset, from_discovery=True)
    db.commit()
    return {"id": asset.id, "data_categories": cats}
