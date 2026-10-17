"""Auditor workspace: evidence requests with comments, the requirements matrix / SoA export, and evidence packs."""
import hashlib
import io
import json
import random
import re
import secrets
import uuid
import zipfile
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from app.deps import DB, Ctx, ensure_member, get_owned
from app.models import (
    Control,
    Evidence,
    EvidenceRequest,
    EvidenceSample,
    EvidenceSampleItem,
    Framework,
    OrgFramework,
    RequestComment,
    User,
)
from app.services import audit, evidence_checks, evidence_review, notify, storage
from app.services.compliance import org_health, requirement_status_rows

router = APIRouter(tags=["audit"])

MAX_PACK_BYTES = 500 * 1024 * 1024


def _can_request(ctx) -> bool:
    return ctx.role == "auditor" or ctx.is_admin


def _req_out(db, r: EvidenceRequest, comments: bool = False) -> dict:
    names = {}
    ids = {i for i in (r.requested_by_id, r.assignee_id) if i}
    if comments:
        rows = db.scalars(select(RequestComment).where(RequestComment.request_id == r.id)
                          .order_by(RequestComment.created_at)).all()
        ids |= {c.user_id for c in rows if c.user_id}
    if ids:
        names = dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())
    control = db.get(Control, r.control_id) if r.control_id else None
    evidence = db.scalars(select(Evidence).where(Evidence.org_id == r.org_id, Evidence.id.in_(
        [uuid.UUID(i) for i in r.evidence_ids]))).all() if r.evidence_ids else []
    out = {"id": r.id, "number": r.number, "ref": f"REQ-{r.number}", "title": r.title, "description": r.description,
           "framework_code": r.framework_code, "requirement_ref": r.requirement_ref, "status": r.status,
           "control": {"id": control.id, "code": control.code, "title": control.title} if control else None,
           "requested_by": names.get(r.requested_by_id), "assignee_id": r.assignee_id,
           "assignee": names.get(r.assignee_id), "due_date": r.due_date, "created_at": r.created_at,
           "updated_at": r.updated_at,
           "evidence": [{"id": e.id, "title": e.title, "kind": e.kind, "file_name": e.file_name,
                         "collected_at": e.collected_at, "control_id": e.control_id} for e in evidence]}
    if comments:
        out["comments"] = [{"id": c.id, "author": names.get(c.user_id, "Deleted user"), "body": c.body,
                            "created_at": c.created_at} for c in rows]
    return out


class RequestIn(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=10000)
    framework_code: str = Field(default="", max_length=50)
    requirement_ref: str = Field(default="", max_length=50)
    control_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    due_date: date | None = None


@router.get("/audit/requests")
def list_requests(db: DB, ctx: Ctx, status_filter: str | None = None):
    q = select(EvidenceRequest).where(EvidenceRequest.org_id == ctx.org_id)
    if status_filter:
        q = q.where(EvidenceRequest.status == status_filter)
    return [_req_out(db, r) for r in db.scalars(q.order_by(EvidenceRequest.number.desc()))]


@router.post("/audit/requests", status_code=201)
def create_request(body: RequestIn, background: BackgroundTasks, db: DB, ctx: Ctx):
    if not _can_request(ctx):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only auditors and admins can raise evidence requests")
    ensure_member(db, ctx, body.assignee_id)
    if body.control_id:
        get_owned(db, Control, body.control_id, ctx)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"evidence-request:{ctx.org_id}"})
    number = (db.scalar(select(func.max(EvidenceRequest.number)).where(EvidenceRequest.org_id == ctx.org_id)) or 0) + 1
    r = EvidenceRequest(org_id=ctx.org_id, number=number, requested_by_id=ctx.user.id, **body.model_dump())
    db.add(r)
    db.flush()
    audit.record(db, ctx, "audit_request.created", r, ref=f"REQ-{number}", title=r.title)
    to = [e for e in [db.scalar(select(User.email).where(User.id == r.assignee_id))] if e] if r.assignee_id \
        else notify.admin_emails(db, ctx.org_id)
    notify.queue(db, ctx.org_id, key=f"req:{r.id}:created", event="evidence_request", to=to,
                 title=f"Evidence requested by {ctx.user.full_name}: REQ-{number} {r.title}",
                 body=r.description[:1000], link=f"/audit/requests/{r.id}")
    db.commit()
    return _req_out(db, r)


@router.get("/audit/requests/{request_id}")
def get_request(request_id: uuid.UUID, db: DB, ctx: Ctx):
    return _req_out(db, get_owned(db, EvidenceRequest, request_id, ctx), comments=True)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


@router.post("/audit/requests/{request_id}/comments", status_code=201)
def comment(request_id: uuid.UUID, body: CommentIn, db: DB, ctx: Ctx):
    r = get_owned(db, EvidenceRequest, request_id, ctx)
    if not (ctx.can_write or ctx.role == "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read-only access")
    db.add(RequestComment(org_id=ctx.org_id, request_id=r.id, user_id=ctx.user.id, body=body.body.strip()))
    r.updated_at = datetime.now(timezone.utc)
    others = {i for i in (r.requested_by_id, r.assignee_id) if i and i != ctx.user.id}
    emails = list(db.scalars(select(User.email).where(User.id.in_(others)))) if others else []
    if emails:
        n = db.scalar(select(func.count(RequestComment.id)).where(RequestComment.request_id == r.id))
        notify.queue(db, ctx.org_id, key=f"req:{r.id}:comment:{n}", event="evidence_request", to=emails,
                     title=f"{ctx.user.full_name} commented on REQ-{r.number}", body=body.body[:1000],
                     link=f"/audit/requests/{r.id}")
    audit.record(db, ctx, "audit_request.commented", r)
    db.commit()
    return _req_out(db, r, comments=True)


class SubmitIn(BaseModel):
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=5000)


@router.post("/audit/requests/{request_id}/submit")
def submit(request_id: uuid.UUID, body: SubmitIn, db: DB, ctx: Ctx):
    if not ctx.can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read-only access")
    r = get_owned(db, EvidenceRequest, request_id, ctx)
    if r.status == "accepted":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This request is already accepted")
    found = set(db.scalars(select(Evidence.id).where(Evidence.org_id == ctx.org_id,
                                                     Evidence.id.in_(body.evidence_ids))))
    if found != set(body.evidence_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Some evidence items were not found")
    r.evidence_ids = sorted({*r.evidence_ids, *(str(i) for i in body.evidence_ids)})
    r.status = "submitted"
    if body.note.strip():
        db.add(RequestComment(org_id=ctx.org_id, request_id=r.id, user_id=ctx.user.id, body=body.note.strip()))
    if r.requested_by_id:
        email = db.scalar(select(User.email).where(User.id == r.requested_by_id))
        notify.queue(db, ctx.org_id, key=f"req:{r.id}:submitted:{len(r.evidence_ids)}", event="evidence_request",
                     to=[email] if email else [], title=f"Evidence submitted for REQ-{r.number} {r.title}",
                     link=f"/audit/requests/{r.id}")
    audit.record(db, ctx, "audit_request.submitted", r, evidence=len(body.evidence_ids))
    db.commit()
    return _req_out(db, r, comments=True)


class DecisionIn(BaseModel):
    decision: Literal["accepted", "rejected"]
    comment: str = Field(default="", max_length=5000)


@router.post("/audit/requests/{request_id}/decision")
def decide(request_id: uuid.UUID, body: DecisionIn, db: DB, ctx: Ctx):
    if not _can_request(ctx):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only auditors and admins can accept or reject evidence")
    r = get_owned(db, EvidenceRequest, request_id, ctx)
    if r.status != "submitted":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only submitted requests can be accepted or rejected")
    if body.decision == "rejected" and not body.comment.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say what is missing when rejecting evidence")
    r.status = body.decision if body.decision == "accepted" else "open"
    if body.comment.strip():
        db.add(RequestComment(org_id=ctx.org_id, request_id=r.id, user_id=ctx.user.id,
                              body=f"[{body.decision}] {body.comment.strip()}"))
    if r.assignee_id:
        email = db.scalar(select(User.email).where(User.id == r.assignee_id))
        notify.queue(db, ctx.org_id, key=f"req:{r.id}:{body.decision}:{datetime.now(timezone.utc):%Y%m%d%H%M%S}",
                     event="evidence_request", to=[email] if email else [],
                     title=f"REQ-{r.number} {body.decision}: {r.title}", body=body.comment[:1000],
                     link=f"/audit/requests/{r.id}")
    audit.record(db, ctx, f"audit_request.{body.decision}", r)
    db.commit()
    return _req_out(db, r, comments=True)


# ================================================================ exports


def _framework(db, ctx, code: str) -> Framework:
    fw = db.scalar(select(Framework).join(OrgFramework, OrgFramework.framework_id == Framework.id)
                   .where(OrgFramework.org_id == ctx.org_id, Framework.code == code))
    if not fw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Framework not enabled")
    return fw


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:80] or "file"


def _xlsx_cell(v):
    """Neutralise spreadsheet formula injection in user-controlled text."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


STATUS_LABEL = {"met": "Met", "partial": "Partly met", "not_met": "Not met", "not_applicable": "Not applicable"}


@router.get("/audit/frameworks/{code}/matrix.xlsx")
def matrix_xlsx(code: str, db: DB, ctx: Ctx):
    """Requirements matrix. For ISO 27001 this doubles as the Statement of Applicability."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    fw = _framework(db, ctx, code)
    rows = requirement_status_rows(db, ctx.org, fw)
    controls, health = org_health(db, ctx.org_id)
    by_id = {c.id: c for c in controls}
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement of Applicability" if fw.code.startswith("iso27001") else "Requirements"
    ws.append([f"{ctx.org.name}: {fw.name}"])
    ws.append([f"Generated {datetime.now(timezone.utc):%d %b %Y %H:%M} UTC by {ctx.user.full_name}. "
               "Status is derived from control implementation, current evidence and automated checks."])
    ws.append([])
    header = ["Ref", "Section", "Requirement", "Applicable", "Justification (if not applicable)", "Status",
              "Controls", "Implementation notes", "Current evidence items", "Control owners"]
    ws.append(header)
    for cell in ws[4]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
    ws["A1"].font = Font(bold=True, size=14)
    for r in rows:
        linked = [by_id[c["id"]] for c in r["controls"] if c["id"] in by_id]
        applicable = r["status"] != "not_applicable" and not all(c.status == "not_applicable" for c in linked
                                                                  if linked)
        justification = "; ".join(f"{c.code}: {c.na_justification}" for c in linked if c.na_justification)
        if r["status"] == "not_applicable" and r["condition"]:
            justification = justification or f"Applies only when: {r['condition']}"
        ws.append([_xlsx_cell(x) for x in [
            r["ref"], r["section"], r["title"], "Yes" if applicable else "No", justification,
            STATUS_LABEL.get(r["status"], r["status"]),
            ", ".join(f"{c.code} {c.title}" for c in linked),
            "\n".join(f"{c.code}: {c.implementation_notes}" for c in linked if c.implementation_notes),
            sum(health[c.id].valid_evidence for c in linked),
            ", ".join(sorted({c.owner.full_name for c in linked if c.owner})),
        ]])
    for col, width in zip("ABCDEFGHIJ", (10, 22, 60, 11, 40, 13, 45, 50, 12, 24), strict=True):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=5):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A5"
    buf = io.BytesIO()
    wb.save(buf)
    audit.record(db, ctx, "audit.matrix_exported", None, framework=fw.code)
    db.commit()
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_safe_name(fw.code)}-matrix.xlsx"',
                             "Cache-Control": "no-store"})


@router.get("/audit/frameworks/{code}/evidence-pack.zip")
def evidence_pack(code: str, db: DB, ctx: Ctx):
    """Every current evidence item for controls mapped to the framework, with a SHA-256 manifest."""
    if not (ctx.is_admin or ctx.role == "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or auditor access required")
    fw = _framework(db, ctx, code)
    rows = requirement_status_rows(db, ctx.org, fw)
    control_ids = {c["id"] for r in rows for c in r["controls"]}
    today = date.today()
    evidence = db.scalars(select(Evidence).where(
        Evidence.org_id == ctx.org_id, Evidence.control_id.in_(control_ids), Evidence.review_status == "approved",
        (Evidence.valid_until.is_(None)) | (Evidence.valid_until >= today)).order_by(Evidence.collected_at)).all()
    unreviewed = db.scalar(select(func.count(Evidence.id)).where(
        Evidence.org_id == ctx.org_id, Evidence.control_id.in_(control_ids), Evidence.review_status == "pending")) or 0
    people = {u.id: u.email for u in db.scalars(select(User).where(User.id.in_(
        {e.uploaded_by_id for e in evidence} | {e.reviewed_by_id for e in evidence})))}
    controls = {c.id: c for c in db.scalars(select(Control).where(Control.id.in_(control_ids)))}
    buf = io.BytesIO()
    manifest, total = [], 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for e in evidence:
            c = controls[e.control_id]
            folder = f"{_safe_name(c.code)}/"
            entry = {"control": c.code, "title": e.title, "kind": e.kind, "source": e.source,
                     "trust": evidence_review.trust(e),
                     "collected_at": e.collected_at.isoformat(), "valid_until": e.valid_until.isoformat()
                     if e.valid_until else None,
                     "uploaded_by": people.get(e.uploaded_by_id), "reviewed_by": people.get(e.reviewed_by_id),
                     "reviewed_at": e.reviewed_at.isoformat() if e.reviewed_at else None,
                     "self_approved": e.self_approved,
                     "warnings": [x["message"] for x in e.checks or [] if x["severity"] == "warn"],
                     "ai_verdict": (e.ai_check or {}).get("verdict")}
            if e.kind == "file" and e.file_key:
                data = storage.read(ctx.org_id, e.file_key)
                total += len(data)
                if total > MAX_PACK_BYTES:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        "Evidence pack is larger than 500 MB; export per control instead")
                name = f"{folder}{str(e.id)[:8]}-{_safe_name(e.file_name)}"
                if evidence_checks.is_digest(e.sha256):
                    entry["sha256_at_upload"] = e.sha256
                    entry["unchanged_since_upload"] = hashlib.sha256(data).hexdigest() == e.sha256
            else:
                data = json.dumps({**entry, "description": e.description, "url": e.url, "data": e.data},
                                  indent=2, default=str).encode()
                name = f"{folder}{str(e.id)[:8]}-{_safe_name(e.title)}.json"
            z.writestr(name, data)
            manifest.append({**entry, "path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        status_rows = [{"ref": r["ref"], "title": r["title"], "status": r["status"],
                        "controls": [c["code"] for c in r["controls"]]} for r in rows]
        meta = {"organisation": ctx.org.name, "framework": fw.name, "generated_at": datetime.now(timezone.utc)
                .isoformat(), "generated_by": ctx.user.email, "files": manifest, "requirements": status_rows,
                "evidence_awaiting_review": unreviewed}
        meta_bytes = json.dumps(meta, indent=2).encode()
        z.writestr("manifest.json", meta_bytes)
        z.writestr("README.txt", (
            f"Evidence pack: {fw.name} for {ctx.org.name}\n\nmanifest.json lists every file with its SHA-256 hash. "
            "Verify with: sha256sum <file>\nFiles uploaded by people carry the fingerprint taken at upload "
            "(sha256_at_upload) and whether the file is unchanged since then.\nOnly evidence approved by a reviewer "
            f"is included; {unreviewed} item(s) were still awaiting review.\nThe manifest hash below is also "
            "recorded in the platform's tamper-evident audit log.\n\nmanifest.json sha256: "
            f"{hashlib.sha256(meta_bytes).hexdigest()}\n"))
    audit.record(db, ctx, "audit.evidence_pack_exported", None, framework=fw.code, files=len(manifest),
                 manifest_sha256=hashlib.sha256(meta_bytes).hexdigest())
    db.commit()
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{_safe_name(fw.code)}-evidence-{today}.zip"',
        "Cache-Control": "no-store"})


# ================================================================ evidence sampling


class SampleIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    framework_code: str = Field(default="", max_length=50)
    period_start: date
    period_end: date
    size: int = Field(default=25, ge=1, le=200)
    method: Literal["random", "per_control"] = "random"


class SampleResultIn(BaseModel):
    result: Literal["pending", "pass", "exception"]
    note: str = Field(default="", max_length=4000)


def _sampler(ctx) -> None:
    if not (ctx.is_admin or ctx.role == "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or auditor access required")


def _population(db, ctx, body: SampleIn) -> list[Evidence]:
    q = select(Evidence).where(
        Evidence.org_id == ctx.org_id, Evidence.review_status == "approved",
        Evidence.collected_at >= datetime.combine(body.period_start, datetime.min.time(), tzinfo=timezone.utc),
        Evidence.collected_at < datetime.combine(body.period_end, datetime.max.time(), tzinfo=timezone.utc))
    if body.framework_code:
        fw = _framework(db, ctx, body.framework_code)
        ids = {c["id"] for r in requirement_status_rows(db, ctx.org, fw) for c in r["controls"]}
        q = q.where(Evidence.control_id.in_(ids))
    return sorted(db.scalars(q), key=lambda e: str(e.id))


def select_sample(population: list[Evidence], controls: dict, seed: str, size: int, method: str) -> list[Evidence]:
    """Deterministic for a given seed and population, so the selection can be re-performed and checked."""
    rng = random.Random(seed)  # nosec B311 - reproducible audit sampling, not a security use
    if method == "per_control":
        by_control: dict = {}
        for e in population:
            by_control.setdefault(controls[e.control_id].code, []).append(e)
        picked = [rng.choice(by_control[code]) for code in sorted(by_control)]
        rest = [e for e in population if e not in picked]
        picked = picked[:size] if len(picked) >= size else picked + rng.sample(rest, min(size - len(picked),
                                                                                         len(rest)))
        return picked
    return rng.sample(population, min(size, len(population)))


def _sample_out(db, s: EvidenceSample, items: bool = False) -> dict:
    rows = db.scalars(select(EvidenceSampleItem).where(EvidenceSampleItem.sample_id == s.id)
                      .order_by(EvidenceSampleItem.control_code, EvidenceSampleItem.evidence_title)).all()
    counts = {k: sum(1 for r in rows if r.result == k) for k in ("pending", "pass", "exception")}
    out = {"id": s.id, "name": s.name, "framework_code": s.framework_code, "period_start": s.period_start,
           "period_end": s.period_end, "seed": s.seed, "population": s.population, "size": len(rows),
           "created_at": s.created_at, "created_by": s.created_by.full_name if s.created_by else "", **counts}
    if items:
        evs = {e.id: e for e in db.scalars(select(Evidence).where(
            Evidence.id.in_([r.evidence_id for r in rows if r.evidence_id])))}
        users = {u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(
            {e.uploaded_by_id for e in evs.values()} | {e.reviewed_by_id for e in evs.values()}
            | {r.tested_by_id for r in rows})))}
        out["items"] = []
        for r in rows:
            e = evs.get(r.evidence_id)
            out["items"].append({
                "id": r.id, "control_code": r.control_code, "evidence_title": r.evidence_title,
                "result": r.result, "note": r.note, "tested_by": users.get(r.tested_by_id), "tested_at": r.tested_at,
                "evidence": None if e is None else {
                    "id": e.id, "control_id": e.control_id, "kind": e.kind, "trust": evidence_review.trust(e),
                    "file_name": e.file_name, "url": e.url, "description": e.description,
                    "collected_at": e.collected_at, "uploaded_by": users.get(e.uploaded_by_id),
                    "reviewed_by": users.get(e.reviewed_by_id), "self_approved": e.self_approved,
                    "changed_since_sampling": bool(r.sha256) and r.sha256 != e.sha256,
                    "warnings": [x["message"] for x in e.checks or [] if x["severity"] == "warn"],
                    "ai_verdict": (e.ai_check or {}).get("verdict"), "ai_summary": (e.ai_check or {}).get("summary")}})
    return out


@router.get("/audit/samples")
def list_samples(db: DB, ctx: Ctx):
    _sampler(ctx)
    rows = db.scalars(select(EvidenceSample).where(EvidenceSample.org_id == ctx.org_id)
                      .order_by(EvidenceSample.created_at.desc())).all()
    return [_sample_out(db, s) for s in rows]


@router.post("/audit/samples", status_code=201)
def create_sample(body: SampleIn, db: DB, ctx: Ctx):
    _sampler(ctx)
    if body.period_end < body.period_start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The period ends before it starts")
    population = _population(db, ctx, body)
    if not population:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No approved evidence was collected in that period")
    controls = {c.id: c for c in db.scalars(select(Control).where(Control.org_id == ctx.org_id))}
    seed = secrets.token_hex(16)
    picked = select_sample(population, controls, seed, body.size, body.method)
    s = EvidenceSample(org_id=ctx.org_id, name=body.name.strip(), framework_code=body.framework_code,
                       period_start=body.period_start, period_end=body.period_end, seed=seed,
                       population=len(population), created_by_id=ctx.user.id)
    db.add(s)
    db.flush()
    for e in picked:
        db.add(EvidenceSampleItem(org_id=ctx.org_id, sample_id=s.id, evidence_id=e.id,
                                  control_code=controls[e.control_id].code, evidence_title=e.title[:300],
                                  sha256=e.sha256 if evidence_checks.is_digest(e.sha256) else ""))
    audit.record(db, ctx, "audit.sample_created", s, population=len(population), size=len(picked),
                 method=body.method, seed=seed)
    db.commit()
    db.refresh(s)
    return _sample_out(db, s, items=True)


@router.get("/audit/samples/{sample_id}")
def get_sample(sample_id: uuid.UUID, db: DB, ctx: Ctx):
    _sampler(ctx)
    return _sample_out(db, get_owned(db, EvidenceSample, sample_id, ctx), items=True)


@router.put("/audit/samples/{sample_id}/items/{item_id}")
def record_result(sample_id: uuid.UUID, item_id: uuid.UUID, body: SampleResultIn, db: DB, ctx: Ctx):
    _sampler(ctx)
    s = get_owned(db, EvidenceSample, sample_id, ctx)
    item = db.scalar(select(EvidenceSampleItem).where(EvidenceSampleItem.id == item_id,
                                                      EvidenceSampleItem.sample_id == s.id))
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sample item not found")
    if body.result == "exception" and not body.note.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Describe the exception")
    item.result, item.note = body.result, body.note.strip()
    item.tested_by_id, item.tested_at = ctx.user.id, datetime.now(timezone.utc)
    audit.record(db, ctx, "audit.sample_tested", s, control=item.control_code, result=body.result)
    db.commit()
    return {"id": item.id, "result": item.result, "note": item.note, "tested_at": item.tested_at}


@router.get("/audit/samples/{sample_id}/export.xlsx")
def export_sample(sample_id: uuid.UUID, db: DB, ctx: Ctx):
    _sampler(ctx)
    s = get_owned(db, EvidenceSample, sample_id, ctx)
    data = _sample_out(db, s, items=True)
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sample"
    ws.append([_xlsx_cell(f"Evidence sample: {s.name}")])
    for k, v in (("Organisation", ctx.org.name), ("Period", f"{s.period_start} to {s.period_end}"),
                 ("Framework", s.framework_code or "All"), ("Population", data["population"]),
                 ("Sample size", data["size"]), ("Selection seed", s.seed),
                 ("Results", f"{data['pass']} pass, {data['exception']} exceptions, {data['pending']} not tested")):
        ws.append([_xlsx_cell(k), _xlsx_cell(v)])
    ws.append([])
    ws.append(["Control", "Evidence", "Type", "Collected", "Uploaded by", "Approved by", "Warnings", "AI check",
               "Result", "Tester notes", "Tested by", "Tested at"])
    for i in data["items"]:
        e = i["evidence"] or {}
        ws.append([_xlsx_cell(v) for v in (
            i["control_code"], i["evidence_title"], e.get("trust", "deleted"),
            e["collected_at"].date().isoformat() if e.get("collected_at") else "", e.get("uploaded_by") or "",
            (e.get("reviewed_by") or "") + (" (self-approved)" if e.get("self_approved") else ""),
            "; ".join(e.get("warnings") or []), e.get("ai_verdict") or "", i["result"], i["note"],
            i["tested_by"] or "", i["tested_at"].isoformat() if i["tested_at"] else "")])
    buf = io.BytesIO()
    wb.save(buf)
    audit.record(db, ctx, "audit.sample_exported", s)
    db.commit()
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="sample-{_safe_name(s.name)}.xlsx"',
                             "Cache-Control": "no-store"})
