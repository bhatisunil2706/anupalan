import time
import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DB, Ctx, WriterCtx, ensure_assignable, get_owned
from app.integrations import REGISTRY
from app.models import (
    Control,
    Evidence,
    Integration,
    Mapping,
    OrgFramework,
    Requirement,
    Task,
    TestResult,
    User,
)
from app.schemas import (
    ControlBulkUpdate,
    ControlCreate,
    ControlOut,
    ControlUpdate,
    EvidenceDecision,
    EvidenceOut,
    TaskOut,
    UserBrief,
)
from app.services import audit, evidence_ai, evidence_checks, evidence_review, notify, storage
from app.services.compliance import default_valid_until, latest_test_results, org_health, requirement_applies
from app.services.evidence_ai import criteria_for

router = APIRouter(tags=["controls"])


def _framework_index(db, ctx) -> dict[uuid.UUID, list[tuple]]:
    """template_id -> [(framework short name, framework code, requirement)] for enabled frameworks."""
    fw_rows = db.scalars(
        select(OrgFramework).where(OrgFramework.org_id == ctx.org_id).options(selectinload(OrgFramework.framework))
    ).all()
    fws = {o.framework_id: o.framework for o in fw_rows}
    index: dict[uuid.UUID, list[tuple]] = defaultdict(list)
    if not fws:
        return index
    rows = db.execute(
        select(Mapping.control_template_id, Requirement)
        .join(Requirement, Mapping.requirement_id == Requirement.id)
        .where(Requirement.framework_id.in_(fws.keys()))
        .order_by(Requirement.order)
    ).all()
    for tpl_id, req in rows:
        if requirement_applies(req, ctx.org):
            fw = fws[req.framework_id]
            index[tpl_id].append((fw.short_name, fw.code, req))
    return index


def _control_out(c: Control, h, index) -> ControlOut:
    refs = index.get(c.template_id, []) if c.template_id else []
    return ControlOut(
        id=c.id, code=c.code, title=c.title, description=c.description, category=c.category,
        frequency=c.frequency, status=c.status, health=h.health,
        owner=UserBrief.model_validate(c.owner) if c.owner else None, next_review_date=c.next_review_date,
        valid_evidence=h.valid_evidence, total_evidence=h.total_evidence, pending_review=h.pending_review,
        frameworks=sorted({r[0] for r in refs}), automatable=bool(c.template and c.template.automatable),
        failing_tests=h.failing_tests,
    )


@router.get("/controls", response_model=list[ControlOut])
def list_controls(db: DB, ctx: Ctx, framework: str | None = None):
    controls, health = org_health(db, ctx.org_id)
    index = _framework_index(db, ctx)
    out = [_control_out(c, health[c.id], index) for c in controls]
    if framework:
        codes = {tpl for tpl, refs in index.items() if any(r[1] == framework for r in refs)}
        out = [o for o, c in zip(out, controls, strict=True) if c.template_id in codes]
    return out


@router.post("/controls", response_model=ControlOut, status_code=201)
def create_control(body: ControlCreate, db: DB, ctx: WriterCtx):
    if db.scalar(select(Control).where(Control.org_id == ctx.org_id, Control.code == body.code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A control with this code already exists")
    c = Control(org_id=ctx.org_id, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, ctx, "control.created", c, code=c.code)
    db.commit()
    controls, health = org_health(db, ctx.org_id)
    return _control_out(c, health[c.id], {})


@router.get("/controls/{control_id}")
def control_detail(control_id: uuid.UUID, db: DB, ctx: Ctx):
    c = get_owned(db, Control, control_id, ctx)
    controls, health = org_health(db, ctx.org_id)
    index = _framework_index(db, ctx)
    evidence = db.scalars(
        select(Evidence).where(Evidence.control_id == c.id).order_by(Evidence.collected_at.desc())
    ).all()
    tasks = db.scalars(select(Task).where(Task.control_id == c.id).order_by(Task.created_at.desc())).all()
    tests = [t for t in latest_test_results(db, ctx.org_id).values() if c.code in t.control_codes]
    requirements = [
        {"framework": fw_short, "framework_code": fw_code, "ref": r.ref, "title": r.title, "guidance": r.guidance}
        for fw_short, fw_code, r in (index.get(c.template_id, []) if c.template_id else [])
    ]
    criteria = criteria_for(c)
    evidence_out = [_evidence_out(db, ctx, e, c) for e in evidence]
    today = date.today()
    current = [e for e in evidence if e.review_status != "rejected"
               and (e.valid_until is None or e.valid_until >= today)]
    coverage = []
    for i, text_ in enumerate(criteria, start=1):
        shown = [e for e in current if i in (e.criteria_confirmed or [])
                 or any(r.get("n") == i and r.get("met") == "yes" for r in (e.ai_check or {}).get("criteria", []))]
        coverage.append({"n": i, "criterion": text_,
                         "approved": [str(e.id) for e in shown if e.review_status == "approved"],
                         "pending": [str(e.id) for e in shown if e.review_status == "pending"]})
    return {
        "control": _control_out(c, health[c.id], index),
        "implementation_notes": c.implementation_notes,
        "na_justification": c.na_justification,
        "evidence_hint": c.template.evidence_hint if c.template else "",
        "acceptance_criteria": criteria,
        "acceptance_customised": bool(c.acceptance_criteria),
        "criteria_coverage": coverage,
        "automation": _automation_for(db, ctx, c),
        "requirements": requirements,
        "evidence": evidence_out,
        "tasks": [TaskOut.model_validate(t) for t in tasks],
        "tests": [{"key": t.test_key, "title": t.title, "status": t.status, "run_at": t.run_at,
                   "summary": t.details.get("summary", "")} for t in tests],
    }


def _evidence_out(db, ctx, ev: Evidence, control: Control) -> EvidenceOut:
    out = EvidenceOut.model_validate(ev)
    out.trust = evidence_review.trust(ev)
    if ev.review_status == "pending" and ctx.role != "auditor":
        out.can_review = evidence_review.permission(db, ctx, ev, control)[0]
    return out


def _automation_for(db, ctx, c: Control) -> list[dict]:
    """Integrations that can collect evidence for this control, and whether they're connected."""
    connected = set(db.scalars(select(Integration.provider).where(Integration.org_id == ctx.org_id,
                                                                  Integration.status != "disabled")))
    out = []
    for provider, cls in REGISTRY.items():
        tests = [t.title for t in cls.tests if c.code in t.control_codes]
        if tests:
            out.append({"provider": provider, "name": cls.name, "connected": provider in connected,
                        "tests": tests[:4]})
    return sorted(out, key=lambda x: (not x["connected"], x["name"]))[:8]


def _notify_owner(db, ctx, controls: list[Control], owner_id) -> None:
    """Tell the new owner what they were given (not when people assign controls to themselves)."""
    if not owner_id or owner_id == ctx.user.id or not controls:
        return
    owner = db.get(User, owner_id)
    if not owner:
        return
    who = ctx.user.full_name or ctx.user.email
    if len(controls) == 1:
        c = controls[0]
        title, link = f"{who} assigned you control {c.code}: {c.title}", f"/controls/{c.id}"
    else:
        title, link = f"{who} assigned you {len(controls)} controls", "/controls?owner=me"
    body = "\n".join(f"{c.code} {c.title}" for c in controls[:50])
    stamp = "-".join(sorted(str(c.id)[:8] for c in controls))[:120]
    notify.queue(db, ctx.org_id, key=f"control-owner:{owner_id}:{stamp}:{int(time.time())}",
                 event="control_assigned", title=title, body=body, link=link, to=[owner.email])


@router.patch("/controls/{control_id}", response_model=ControlOut)
def update_control(control_id: uuid.UUID, body: ControlUpdate, db: DB, ctx: WriterCtx):
    c = get_owned(db, Control, control_id, ctx)
    data = body.model_dump(exclude_unset=True)
    if data.pop("clear_owner", False):
        data["owner_id"] = None
    if "acceptance_criteria" in data:
        data["acceptance_criteria"] = [x.strip()[:300] for x in (data["acceptance_criteria"] or []) if x.strip()]
    for k in ("title", "category"):
        if k in data:
            if data[k] is None or not data[k].strip():
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{k.capitalize()} can't be empty")
            data[k] = data[k].strip()
    new_owner = "owner_id" in data and data["owner_id"] != c.owner_id
    if new_owner:
        ensure_assignable(db, ctx, data["owner_id"])
    if data.get("status") == "not_applicable" and not (data.get("na_justification") or c.na_justification).strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A justification is required to mark a control not applicable")
    before = {k: getattr(c, k) for k in data}
    for k, v in data.items():
        setattr(c, k, v)
    changed = [k for k in data if before[k] != data[k]]
    audit.record(db, ctx, "control.updated", c, code=c.code, fields=changed,
                 **({"owner_id": str(c.owner_id) if c.owner_id else None} if new_owner else {}))
    db.flush()
    if new_owner:
        _notify_owner(db, ctx, [c], c.owner_id)
    db.commit()
    db.refresh(c)
    controls, health = org_health(db, ctx.org_id)
    return _control_out(c, health[c.id], _framework_index(db, ctx))


@router.post("/controls/bulk")
def bulk_update(body: ControlBulkUpdate, db: DB, ctx: WriterCtx):
    """Assign an owner, set a status or a review date on many controls at once."""
    data = body.model_dump(exclude_unset=True, exclude={"ids"})
    if data.pop("clear_owner", False):
        data["owner_id"] = None
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to change")
    if data.get("owner_id"):
        ensure_assignable(db, ctx, data["owner_id"])
    controls = db.scalars(select(Control).where(Control.org_id == ctx.org_id, Control.id.in_(set(body.ids)))).all()
    if len(controls) != len(set(body.ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Some controls were not found")
    reassigned = [c for c in controls if "owner_id" in data and c.owner_id != data["owner_id"]]
    for c in controls:
        for k, v in data.items():
            setattr(c, k, v)
    audit.record(db, ctx, "control.bulk_updated", None, count=len(controls), codes=sorted(c.code for c in controls),
                 fields=sorted(data), **({"owner_id": str(data["owner_id"])} if data.get("owner_id") else {}))
    db.flush()
    if data.get("owner_id"):
        _notify_owner(db, ctx, reassigned, data["owner_id"])
    db.commit()
    return {"updated": len(controls)}


# ---------------------------------------------------------------- evidence


@router.post("/controls/{control_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(
    control_id: uuid.UUID,
    db: DB,
    ctx: WriterCtx,
    title: str = Form(..., max_length=300),
    kind: str = Form("file"),
    description: str = Form(""),
    url: str = Form(""),
    valid_until: date | None = Form(None),
    criteria: str = Form("", max_length=200),
    file: UploadFile | None = File(None),
):
    c = get_owned(db, Control, control_id, ctx)
    if kind not in ("file", "link", "note"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind must be file, link or note")
    ev = Evidence(org_id=ctx.org_id, control_id=c.id, title=title.strip(), description=description, kind=kind,
                  source="manual", uploaded_by_id=ctx.user.id,
                  valid_until=valid_until or default_valid_until(c.frequency))
    data = None
    if kind == "file":
        if not file:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A file is required")
        ev.file_key, ev.file_name, ev.size_bytes, data = storage.save_upload(ctx.org_id, file, return_data=True)
        ev.content_type = storage.content_type_for(ev.file_name)
    elif kind == "link":
        if not url.startswith(("https://", "http://")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid http(s) URL is required")
        ev.url = url
    elif not description.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A note needs a description")
    n_criteria = len(criteria_for(c))
    try:
        picked = sorted({int(x) for x in criteria.split(",") if x.strip()})
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "criteria must be numbers") from e
    if any(not 1 <= n <= n_criteria for n in picked):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown acceptance criterion")
    ev.criteria_confirmed = picked
    ev.review_status = "pending" if evidence_review.needs_review(ctx.org, ev) else "approved"
    db.add(ev)
    db.flush()
    evidence_checks.evaluate(db, ev, c, data)
    queued = evidence_ai.queue_check(db, ctx.org, ev, ctx.user.id)
    if ev.review_status == "pending":
        evidence_review.notify_pending(db, ctx, ev, c)
    audit.record(db, ctx, "evidence.added", ev, control=c.code, kind=kind, sha256=ev.sha256 or None,
                 review=ev.review_status, warnings=[x["code"] for x in ev.checks if x["severity"] == "warn"],
                 ai_check=queued)
    db.commit()
    db.refresh(ev)
    return _evidence_out(db, ctx, ev, c)


@router.get("/evidence", response_model=list[EvidenceOut])
def list_evidence(db: DB, ctx: Ctx):
    rows = db.scalars(
        select(Evidence).where(Evidence.org_id == ctx.org_id).order_by(Evidence.collected_at.desc()).limit(500)
    ).all()
    controls = {c.id: c for c in db.scalars(select(Control).where(Control.org_id == ctx.org_id))}
    return [_evidence_out(db, ctx, e, controls[e.control_id]) for e in rows]


@router.get("/evidence/review-queue")
def review_queue(db: DB, ctx: Ctx):
    """Evidence waiting for a second person, with the automatic and AI check results."""
    rows = db.execute(select(Evidence, Control).join(Control, Control.id == Evidence.control_id)
                      .where(Evidence.org_id == ctx.org_id, Evidence.review_status == "pending")
                      .order_by(Evidence.collected_at)).all()
    out = []
    for ev, c in rows:
        e = _evidence_out(db, ctx, ev, c).model_dump()
        e.update(control={"id": c.id, "code": c.code, "title": c.title}, acceptance_criteria=criteria_for(c),
                 warnings=sum(1 for x in ev.checks or [] if x["severity"] == "warn")
                 + (1 if (ev.ai_check or {}).get("verdict") in ("needs_attention", "wrong_evidence") else 0))
        out.append(e)
    recent = db.execute(select(Evidence, Control).join(Control, Control.id == Evidence.control_id)
                        .where(Evidence.org_id == ctx.org_id, Evidence.review_status.in_(("approved", "rejected")),
                               Evidence.reviewed_at.is_not(None))
                        .order_by(Evidence.reviewed_at.desc()).limit(20)).all()
    return {"pending": out, "require_review": ctx.org.require_evidence_review,
            "ai_checks": bool(ctx.org.ai_enabled and ctx.org.ai_evidence_checks),
            "recent": [{**_evidence_out(db, ctx, ev, c).model_dump(),
                        "control": {"id": c.id, "code": c.code, "title": c.title}} for ev, c in recent]}


@router.get("/evidence/review-count")
def review_count(db: DB, ctx: Ctx):
    """For the navigation badge: evidence waiting for review, and how many the current user can review."""
    rows = db.execute(select(Evidence, Control).join(Control, Control.id == Evidence.control_id)
                      .where(Evidence.org_id == ctx.org_id, Evidence.review_status == "pending")).all()
    mine = 0 if ctx.role == "auditor" else sum(1 for ev, c in rows if evidence_review.permission(db, ctx, ev, c)[0])
    return {"pending": len(rows), "mine": mine}


@router.post("/evidence/{evidence_id}/review", response_model=EvidenceOut)
def review_evidence(evidence_id: uuid.UUID, body: EvidenceDecision, db: DB, ctx: WriterCtx):
    ev = get_owned(db, Evidence, evidence_id, ctx)
    c = db.get(Control, ev.control_id)
    if body.decision == "reject" and not body.note.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say why you're sending it back")
    try:
        evidence_review.decide(db, ctx, ev, c, body.decision == "approve", body.note)
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from e
    audit.record(db, ctx, f"evidence.{'approved' if body.decision == 'approve' else 'rejected'}", ev,
                 control=c.code, self_approved=ev.self_approved, note=body.note[:500] or None)
    db.commit()
    db.refresh(ev)
    return _evidence_out(db, ctx, ev, c)


@router.post("/evidence/{evidence_id}/recheck", response_model=EvidenceOut)
def recheck_evidence(evidence_id: uuid.UUID, db: DB, ctx: WriterCtx):
    """Run the automatic checks again (and the AI check, when turned on)."""
    ev = get_owned(db, Evidence, evidence_id, ctx)
    c = db.get(Control, ev.control_id)
    data = storage.read(ctx.org_id, ev.file_key) if ev.file_key else None
    if data is not None and evidence_checks.is_digest(ev.sha256) and evidence_checks.sha256(data) != ev.sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "The stored file no longer matches its fingerprint")
    keep_sha = ev.sha256
    evidence_checks.evaluate(db, ev, c, data)
    ev.sha256 = keep_sha or ev.sha256
    if ev.kind == "link":
        result = evidence_checks.check_link(ev.url)
        ev.checks = [x for x in ev.checks if not x["code"].startswith("link_")] + ([result] if result else [])
    evidence_ai.queue_check(db, ctx.org, ev, ctx.user.id)
    audit.record(db, ctx, "evidence.rechecked", ev)
    db.commit()
    db.refresh(ev)
    return _evidence_out(db, ctx, ev, c)


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: uuid.UUID, db: DB, ctx: Ctx):
    ev = get_owned(db, Evidence, evidence_id, ctx)
    if not ev.file_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No file attached")
    data = storage.read(ctx.org_id, ev.file_key)
    if evidence_checks.is_digest(ev.sha256) and evidence_checks.sha256(data) != ev.sha256:
        audit.record(db, ctx, "evidence.integrity_failed", ev, title=ev.title)
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "This file doesn't match the fingerprint taken when it was "
                                                      "uploaded. It may have been altered; contact support.")
    audit.record(db, ctx, "evidence.downloaded", ev, title=ev.title)
    db.commit()
    return storage.download_response(ctx.org_id, ev.file_key, ev.file_name, data=data,
                                     extra_headers={"X-Evidence-SHA256": ev.sha256} if ev.sha256 else None)


@router.delete("/evidence/{evidence_id}", status_code=204)
def delete_evidence(evidence_id: uuid.UUID, db: DB, ctx: WriterCtx):
    ev = get_owned(db, Evidence, evidence_id, ctx)
    if ev.kind in ("automated", "policy"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "System-generated evidence cannot be deleted")
    storage.delete(ctx.org_id, ev.file_key)
    audit.record(db, ctx, "evidence.deleted", ev, title=ev.title)
    db.delete(ev)
    db.commit()


@router.get("/tests")
def list_tests(db: DB, ctx: Ctx):
    rows = latest_test_results(db, ctx.org_id).values()
    return [{"key": t.test_key, "title": t.title, "status": t.status, "run_at": t.run_at,
             "control_codes": t.control_codes, "summary": t.details.get("summary", "")}
            for t in sorted(rows, key=lambda t: (t.status != "fail", t.test_key))]


_ = TestResult  # re-exported for type checkers
