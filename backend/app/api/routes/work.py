"""Tasks, policies, risks and vendors."""
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.deps import DB, AdminCtx, Ctx, WriterCtx, ensure_assignable, ensure_member, get_owned
from app.models import (
    Control,
    Membership,
    Policy,
    PolicyAcknowledgment,
    PolicyTemplate,
    Risk,
    Task,
    User,
    Vendor,
)
from app.schemas import (
    FromTemplateIn,
    PolicyIn,
    PolicyOut,
    PolicyUpdate,
    RiskIn,
    RiskOut,
    TaskIn,
    TaskOut,
    TaskUpdate,
    VendorIn,
    VendorOut,
)
from app.services import audit, doc_import, notify
from app.services.policies import approve_policy, create_policy_from_template

router = APIRouter()


# ================================================================ tasks


def _task_out(t: Task) -> TaskOut:
    out = TaskOut.model_validate(t)
    out.control_code = t.control.code if t.control else None
    return out


@router.get("/tasks", response_model=list[TaskOut], tags=["tasks"])
def list_tasks(db: DB, ctx: Ctx, status_filter: str | None = None, mine: bool = False):
    q = select(Task).where(Task.org_id == ctx.org_id)
    if status_filter == "active":
        q = q.where(Task.status != "done")
    elif status_filter:
        q = q.where(Task.status == status_filter)
    if mine:
        q = q.where(Task.assignee_id == ctx.user.id)
    q = q.order_by(Task.status == "done", Task.due_date.is_(None), Task.due_date, Task.created_at.desc())
    return [_task_out(t) for t in db.scalars(q.limit(500))]


def _notify_assignee(db, ctx, t: Task) -> None:
    if t.assignee_id and t.assignee_id != ctx.user.id:
        email = db.scalar(select(User.email).where(User.id == t.assignee_id))
        notify.queue(db, ctx.org_id, key=f"task:{t.id}:assigned:{t.assignee_id}", event="task_assigned",
                     to=[email], title=f"{ctx.user.full_name} assigned you a task: {t.title}",
                     body=t.description, link="/tasks")


def _check_control(db, ctx, control_id):
    if control_id is not None:
        get_owned(db, Control, control_id, ctx)


@router.post("/tasks", response_model=TaskOut, status_code=201, tags=["tasks"])
def create_task(body: TaskIn, db: DB, ctx: WriterCtx):
    ensure_member(db, ctx, body.assignee_id)
    _check_control(db, ctx, body.control_id)
    t = Task(org_id=ctx.org_id, **body.model_dump())
    db.add(t)
    db.flush()
    _notify_assignee(db, ctx, t)
    audit.record(db, ctx, "task.created", t, title=t.title)
    db.commit()
    db.refresh(t)
    return _task_out(t)


@router.patch("/tasks/{task_id}", response_model=TaskOut, tags=["tasks"])
def update_task(task_id: uuid.UUID, body: TaskUpdate, db: DB, ctx: WriterCtx):
    t = get_owned(db, Task, task_id, ctx)
    data = body.model_dump(exclude_unset=True)
    if "assignee_id" in data:
        ensure_member(db, ctx, data["assignee_id"])
    for k, v in data.items():
        setattr(t, k, v)
    if "assignee_id" in data:
        _notify_assignee(db, ctx, t)
    if data.get("status") == "done" and not t.completed_at:
        t.completed_at = datetime.now(timezone.utc)
    elif data.get("status") in ("open", "in_progress"):
        t.completed_at = None
    db.commit()
    db.refresh(t)
    return _task_out(t)


@router.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
def delete_task(task_id: uuid.UUID, db: DB, ctx: WriterCtx):
    t = get_owned(db, Task, task_id, ctx)
    db.delete(t)
    db.commit()


# ================================================================ policies


def _policy_out(db, ctx, p: Policy) -> PolicyOut:
    out = PolicyOut.model_validate(p)
    out.member_count = db.scalar(select(func.count()).select_from(Membership).where(Membership.org_id == ctx.org_id))
    acks = db.scalars(
        select(PolicyAcknowledgment.user_id).where(PolicyAcknowledgment.policy_id == p.id,
                                                   PolicyAcknowledgment.version == p.version)
    ).all()
    out.acknowledged_count = len(acks)
    out.acknowledged_by_me = ctx.user.id in acks
    return out


@router.get("/policies", response_model=list[PolicyOut], tags=["policies"])
def list_policies(db: DB, ctx: Ctx):
    return [_policy_out(db, ctx, p)
            for p in db.scalars(select(Policy).where(Policy.org_id == ctx.org_id).order_by(Policy.title))]


@router.get("/policies/templates", tags=["policies"])
def policy_templates(db: DB, ctx: Ctx):
    have = set(db.scalars(select(Policy.slug).where(Policy.org_id == ctx.org_id)))
    return [{"slug": t.slug, "title": t.title, "control_codes": t.control_codes, "added": t.slug in have}
            for t in db.scalars(select(PolicyTemplate).order_by(PolicyTemplate.title))]


@router.post("/policies/from-template", response_model=PolicyOut, status_code=201, tags=["policies"])
def policy_from_template(body: FromTemplateIn, db: DB, ctx: WriterCtx):
    tpl = db.scalar(select(PolicyTemplate).where(PolicyTemplate.slug == body.slug))
    if not tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    p = create_policy_from_template(db, ctx, tpl)
    audit.record(db, ctx, "policy.created", p, template=tpl.slug)
    db.commit()
    return _policy_out(db, ctx, p)


def _valid_codes(db, ctx, codes: list[str]) -> list[str]:
    wanted = sorted({c.strip().upper() for c in codes if c and c.strip()})
    if not wanted:
        return []
    known = set(db.scalars(select(Control.code).where(Control.org_id == ctx.org_id, Control.code.in_(wanted))))
    unknown = [c for c in wanted if c not in known]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown control codes: {', '.join(unknown)}")
    return wanted


IMPORT_MAX_BYTES = 10 * 1024 * 1024


@router.post("/policies/import", tags=["policies"])
async def import_policy_document(ctx: WriterCtx, file: UploadFile = File(...)):
    """Convert a Word (.docx) or PDF file into editor content. Nothing is saved until the user saves the policy."""
    data = await file.read(IMPORT_MAX_BYTES + 1)
    if len(data) > IMPORT_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Files up to 10 MB can be imported")
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")
    try:
        result = doc_import.convert(file.filename or "", data)
    except doc_import.ImportError_ as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    title = re.sub(r"[_-]+", " ", (file.filename or "").rsplit(".", 1)[0]).strip()[:200]
    return {**result, "title": title}


@router.post("/policies", response_model=PolicyOut, status_code=201, tags=["policies"])
def create_policy(body: PolicyIn, db: DB, ctx: WriterCtx):
    slug = "custom-" + uuid.uuid4().hex[:8]
    ensure_assignable(db, ctx, body.owner_id)
    p = Policy(org_id=ctx.org_id, slug=slug, title=body.title.strip(), body_md=body.body_md,
               control_codes=_valid_codes(db, ctx, body.control_codes), owner_id=body.owner_id or ctx.user.id)
    db.add(p)
    db.flush()
    audit.record(db, ctx, "policy.created", p)
    db.commit()
    return _policy_out(db, ctx, p)


@router.get("/policies/{policy_id}", response_model=PolicyOut, tags=["policies"])
def get_policy(policy_id: uuid.UUID, db: DB, ctx: Ctx):
    return _policy_out(db, ctx, get_owned(db, Policy, policy_id, ctx))


@router.patch("/policies/{policy_id}", response_model=PolicyOut, tags=["policies"])
def update_policy(policy_id: uuid.UUID, body: PolicyUpdate, db: DB, ctx: WriterCtx):
    p = get_owned(db, Policy, policy_id, ctx)
    data = body.model_dump(exclude_unset=True)
    if data.pop("clear_owner", False):
        data["owner_id"] = None
    if data.get("owner_id"):
        ensure_assignable(db, ctx, data["owner_id"])
    if "title" in data:
        if not (data["title"] or "").strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Title can't be empty")
        data["title"] = data["title"].strip()
    if "body_md" in data and data["body_md"] is None:
        data.pop("body_md")
    if "control_codes" in data:
        data["control_codes"] = _valid_codes(db, ctx, data["control_codes"] or [])
    content_changed = any(k in data and data[k] != getattr(p, k) for k in ("title", "body_md"))
    for k, v in data.items():
        setattr(p, k, v)
    if content_changed and p.status == "approved":
        # Editing an approved policy starts a new draft version; the approved evidence stays until it expires.
        p.version += 1
        p.status = "draft"
        p.approved_at = None
        p.approved_by_id = None
    audit.record(db, ctx, "policy.updated", p, version=p.version)
    db.commit()
    db.refresh(p)
    return _policy_out(db, ctx, p)


@router.post("/policies/{policy_id}/approve", response_model=PolicyOut, tags=["policies"])
def approve(policy_id: uuid.UUID, db: DB, ctx: AdminCtx):
    p = get_owned(db, Policy, policy_id, ctx)
    approve_policy(db, ctx, p)
    emails = list(db.scalars(select(User.email).join(Membership, Membership.user_id == User.id)
                             .where(Membership.org_id == ctx.org_id)))
    notify.queue(db, ctx.org_id, key=f"policy:{p.id}:v{p.version}:approved", event="policy_approved", to=emails,
                 title=f"Please read and acknowledge: {p.title} (version {p.version})",
                 link=f"/policies/{p.id}")
    audit.record(db, ctx, "policy.approved", p, version=p.version)
    db.commit()
    db.refresh(p)
    return _policy_out(db, ctx, p)


@router.post("/policies/{policy_id}/acknowledge", response_model=PolicyOut, tags=["policies"])
def acknowledge(policy_id: uuid.UUID, db: DB, ctx: Ctx):
    p = get_owned(db, Policy, policy_id, ctx)
    if p.status != "approved":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only approved policies can be acknowledged")
    exists = db.scalar(select(PolicyAcknowledgment).where(
        PolicyAcknowledgment.policy_id == p.id, PolicyAcknowledgment.user_id == ctx.user.id,
        PolicyAcknowledgment.version == p.version))
    if not exists:
        db.add(PolicyAcknowledgment(org_id=ctx.org_id, policy_id=p.id, user_id=ctx.user.id, version=p.version))
        audit.record(db, ctx, "policy.acknowledged", p, version=p.version)
        db.commit()
    return _policy_out(db, ctx, p)


@router.delete("/policies/{policy_id}", status_code=204, tags=["policies"])
def delete_policy(policy_id: uuid.UUID, db: DB, ctx: AdminCtx):
    p = get_owned(db, Policy, policy_id, ctx)
    audit.record(db, ctx, "policy.deleted", p, title=p.title)
    db.delete(p)
    db.commit()


# ================================================================ risks


def _risk_out(r: Risk) -> RiskOut:
    out = RiskOut.model_validate(r)
    out.score = r.likelihood * r.impact
    return out


@router.get("/risks", response_model=list[RiskOut], tags=["risks"])
def list_risks(db: DB, ctx: Ctx):
    rows = db.scalars(select(Risk).where(Risk.org_id == ctx.org_id)).all()
    return sorted((_risk_out(r) for r in rows), key=lambda r: (r.status == "closed", -r.score))


@router.post("/risks", response_model=RiskOut, status_code=201, tags=["risks"])
def create_risk(body: RiskIn, db: DB, ctx: WriterCtx):
    ensure_member(db, ctx, body.owner_id)
    r = Risk(org_id=ctx.org_id, **body.model_dump())
    db.add(r)
    db.flush()
    audit.record(db, ctx, "risk.created", r, title=r.title)
    db.commit()
    db.refresh(r)
    return _risk_out(r)


@router.put("/risks/{risk_id}", response_model=RiskOut, tags=["risks"])
def update_risk(risk_id: uuid.UUID, body: RiskIn, db: DB, ctx: WriterCtx):
    r = get_owned(db, Risk, risk_id, ctx)
    ensure_member(db, ctx, body.owner_id)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit.record(db, ctx, "risk.updated", r)
    db.commit()
    db.refresh(r)
    return _risk_out(r)


@router.delete("/risks/{risk_id}", status_code=204, tags=["risks"])
def delete_risk(risk_id: uuid.UUID, db: DB, ctx: WriterCtx):
    r = get_owned(db, Risk, risk_id, ctx)
    audit.record(db, ctx, "risk.deleted", r, title=r.title)
    db.delete(r)
    db.commit()


# ================================================================ vendors


@router.get("/vendors", response_model=list[VendorOut], tags=["vendors"])
def list_vendors(db: DB, ctx: Ctx):
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows = db.scalars(select(Vendor).where(Vendor.org_id == ctx.org_id)).all()
    return sorted(rows, key=lambda v: (v.status == "offboarded", order.get(v.tier, 9), v.name.lower()))


@router.post("/vendors", response_model=VendorOut, status_code=201, tags=["vendors"])
def create_vendor(body: VendorIn, db: DB, ctx: WriterCtx):
    ensure_member(db, ctx, body.owner_id)
    v = Vendor(org_id=ctx.org_id, **body.model_dump())
    db.add(v)
    db.flush()
    audit.record(db, ctx, "vendor.created", v, name=v.name)
    db.commit()
    db.refresh(v)
    return v


@router.put("/vendors/{vendor_id}", response_model=VendorOut, tags=["vendors"])
def update_vendor(vendor_id: uuid.UUID, body: VendorIn, db: DB, ctx: WriterCtx):
    v = get_owned(db, Vendor, vendor_id, ctx)
    ensure_member(db, ctx, body.owner_id)
    for k, val in body.model_dump().items():
        setattr(v, k, val)
    audit.record(db, ctx, "vendor.updated", v)
    db.commit()
    db.refresh(v)
    return v


@router.delete("/vendors/{vendor_id}", status_code=204, tags=["vendors"])
def delete_vendor(vendor_id: uuid.UUID, db: DB, ctx: WriterCtx):
    v = get_owned(db, Vendor, vendor_id, ctx)
    audit.record(db, ctx, "vendor.deleted", v, name=v.name)
    db.delete(v)
    db.commit()
