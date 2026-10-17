import time
import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DB, Ctx, WriterCtx, ensure_assignable, get_owned
from app.models import Control, Evidence, Mapping, OrgFramework, Requirement, Task, TestResult, User
from app.schemas import ControlBulkUpdate, ControlCreate, ControlOut, ControlUpdate, EvidenceOut, TaskOut, UserBrief
from app.services import audit, notify, storage
from app.services.compliance import default_valid_until, latest_test_results, org_health, requirement_applies

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
        valid_evidence=h.valid_evidence, total_evidence=h.total_evidence,
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
    return {
        "control": _control_out(c, health[c.id], index),
        "implementation_notes": c.implementation_notes,
        "na_justification": c.na_justification,
        "evidence_hint": c.template.evidence_hint if c.template else "",
        "requirements": requirements,
        "evidence": [EvidenceOut.model_validate(e) for e in evidence],
        "tasks": [TaskOut.model_validate(t) for t in tasks],
        "tests": [{"key": t.test_key, "title": t.title, "status": t.status, "run_at": t.run_at,
                   "summary": t.details.get("summary", "")} for t in tests],
    }


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
    file: UploadFile | None = File(None),
):
    c = get_owned(db, Control, control_id, ctx)
    if kind not in ("file", "link", "note"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "kind must be file, link or note")
    ev = Evidence(org_id=ctx.org_id, control_id=c.id, title=title.strip(), description=description, kind=kind,
                  uploaded_by_id=ctx.user.id, valid_until=valid_until or default_valid_until(c.frequency))
    if kind == "file":
        if not file:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A file is required")
        ev.file_key, ev.file_name, ev.size_bytes = storage.save_upload(ctx.org_id, file)
        ev.content_type = storage.content_type_for(ev.file_name)
    elif kind == "link":
        if not url.startswith(("https://", "http://")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A valid http(s) URL is required")
        ev.url = url
    elif not description.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A note needs a description")
    db.add(ev)
    db.flush()
    audit.record(db, ctx, "evidence.added", ev, control=c.code, kind=kind)
    db.commit()
    db.refresh(ev)
    return ev


@router.get("/evidence", response_model=list[EvidenceOut])
def list_evidence(db: DB, ctx: Ctx):
    return db.scalars(
        select(Evidence).where(Evidence.org_id == ctx.org_id).order_by(Evidence.collected_at.desc()).limit(500)
    ).all()


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: uuid.UUID, db: DB, ctx: Ctx):
    ev = get_owned(db, Evidence, evidence_id, ctx)
    if not ev.file_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No file attached")
    audit.record(db, ctx, "evidence.downloaded", ev, title=ev.title)
    db.commit()
    return storage.download_response(ctx.org_id, ev.file_key, ev.file_name)


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
