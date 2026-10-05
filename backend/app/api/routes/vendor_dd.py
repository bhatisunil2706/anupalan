"""Vendor due diligence: questionnaires sent by link, scoring, review, and certificate/document tracking."""
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app import ratelimit
from app.config import get_settings
from app.db import set_tenant
from app.deps import DB, Ctx, WriterCtx, get_owned
from app.models import Control, Evidence, Organization, QuestionnaireTemplate, Vendor, VendorAssessment, VendorDocument
from app.request_context import client_ip
from app.security import hash_token, new_token
from app.services import audit, notify, storage

router = APIRouter(tags=["vendors"])

DOC_KINDS = {"iso27001": "ISO 27001 certificate", "soc2": "SOC 2 report", "dpa": "Data processing agreement",
             "pentest": "Penetration test summary", "insurance": "Cyber insurance", "other": "Other"}
REVIEW_MONTHS = {"critical": 12, "high": 12, "medium": 24, "low": None}


def score_answers(questions: list[dict], answers: dict) -> tuple[int | None, str, list[str]]:
    """Return (score 0-100, risk rating, ids of critical questions answered badly)."""
    got = possible = 0
    critical_misses = []
    for q in questions:
        if q.get("type") != "yes_no" or not q.get("weight"):
            continue
        a = (answers.get(q["id"]) or {}).get("answer")
        if a == "na":
            continue
        possible += q["weight"]
        if a == q.get("good"):
            got += q["weight"]
        elif q["weight"] >= 3:
            critical_misses.append(q["id"])
    if not possible:
        return None, "", critical_misses
    score = round(100 * got / possible)
    rating = "low" if score >= 85 else "medium" if score >= 65 else "high"
    if critical_misses and rating == "low":
        rating = "medium"
    return score, rating, critical_misses


def _template(db, slug: str) -> QuestionnaireTemplate:
    t = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.slug == slug))
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Questionnaire not found")
    return t


def _assessment_out(a: VendorAssessment, include_answers: bool = False) -> dict:
    out = {"id": a.id, "vendor_id": a.vendor_id, "template_slug": a.template_slug, "sent_to_email": a.sent_to_email,
           "status": a.status, "score": a.score, "rating": a.rating, "expires_at": a.expires_at,
           "submitted_at": a.submitted_at, "reviewed_at": a.reviewed_at, "reviewer_notes": a.reviewer_notes,
           "respondent_name": a.respondent_name, "created_at": a.created_at}
    if include_answers:
        out["answers"] = a.answers
    return out


def _doc_out(d: VendorDocument) -> dict:
    return {"id": d.id, "kind": d.kind, "kind_label": DOC_KINDS.get(d.kind, d.kind), "title": d.title,
            "file_name": d.file_name, "size_bytes": d.size_bytes, "valid_until": d.valid_until,
            "uploaded_via": d.uploaded_via, "created_at": d.created_at}


# ================================================================ in-app


@router.get("/questionnaires")
def templates(db: DB, ctx: Ctx):
    return [{"slug": t.slug, "title": t.title, "description": t.description, "questions": len(t.questions)}
            for t in db.scalars(select(QuestionnaireTemplate).order_by(QuestionnaireTemplate.title))]


@router.get("/vendors/{vendor_id}/detail")
def vendor_detail(vendor_id: uuid.UUID, db: DB, ctx: Ctx):
    v = get_owned(db, Vendor, vendor_id, ctx)
    assessments = db.scalars(select(VendorAssessment).where(VendorAssessment.vendor_id == v.id)
                             .order_by(VendorAssessment.created_at.desc())).all()
    docs = db.scalars(select(VendorDocument).where(VendorDocument.vendor_id == v.id)
                      .order_by(VendorDocument.created_at.desc())).all()
    return {"assessments": [_assessment_out(a) for a in assessments], "documents": [_doc_out(d) for d in docs],
            "doc_kinds": DOC_KINDS}


class SendIn(BaseModel):
    template_slug: str
    email: EmailStr
    expires_days: int = Field(default=21, ge=3, le=60)


@router.post("/vendors/{vendor_id}/assessments", status_code=201)
def send_assessment(vendor_id: uuid.UUID, body: SendIn, background: BackgroundTasks, db: DB, ctx: WriterCtx):
    v = get_owned(db, Vendor, vendor_id, ctx)
    t = _template(db, body.template_slug)
    token, token_hash = new_token()
    a = VendorAssessment(org_id=ctx.org_id, vendor_id=v.id, template_slug=t.slug, token_hash=token_hash,
                         sent_to_email=body.email.lower(), created_by_id=ctx.user.id,
                         expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_days))
    db.add(a)
    db.flush()
    audit.record(db, ctx, "vendor.assessment_sent", a, vendor=v.name, template=t.slug, to=a.sent_to_email)
    db.commit()
    link = f"{get_settings().public_url.rstrip('/')}/q/{token}"
    background.add_task(
        notify.send_email_safely, [a.sent_to_email], f"{ctx.org.name} security questionnaire",
        f"Hello,\n\n{ctx.org.name} has asked {v.name} to complete a short security questionnaire ({t.title}, "
        f"{len(t.questions)} questions). You can save and come back before submitting.\n\n{link}\n\n"
        f"The link expires on {a.expires_at:%d %b %Y}. Please don't forward it outside your organisation.")
    return {**_assessment_out(a), "link": link}


@router.get("/vendors/{vendor_id}/assessments/{assessment_id}")
def assessment(vendor_id: uuid.UUID, assessment_id: uuid.UUID, db: DB, ctx: Ctx):
    a = get_owned(db, VendorAssessment, assessment_id, ctx)
    if a.vendor_id != vendor_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
    t = _template(db, a.template_slug)
    _, _, critical = score_answers(t.questions, a.answers)
    return {**_assessment_out(a, include_answers=True), "template": {"title": t.title, "questions": t.questions},
            "critical_issues": critical}


class ReviewIn(BaseModel):
    notes: str = Field(default="", max_length=5000)


@router.post("/vendors/{vendor_id}/assessments/{assessment_id}/review")
def review_assessment(vendor_id: uuid.UUID, assessment_id: uuid.UUID, body: ReviewIn, db: DB, ctx: WriterCtx):
    a = get_owned(db, VendorAssessment, assessment_id, ctx)
    v = get_owned(db, Vendor, vendor_id, ctx)
    if a.vendor_id != v.id or a.status != "submitted":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only submitted questionnaires can be reviewed")
    a.status, a.reviewed_at, a.reviewed_by_id, a.reviewer_notes = "reviewed", datetime.now(timezone.utc), \
        ctx.user.id, body.notes
    v.last_assessed_at = date.today()
    months = REVIEW_MONTHS.get(v.tier)
    v.next_review_date = date.today() + timedelta(days=round(30.4 * months)) if months else None
    control = db.scalar(select(Control).where(Control.org_id == ctx.org_id, Control.code == "VEN-01"))
    if control:
        db.add(Evidence(org_id=ctx.org_id, control_id=control.id, kind="note", source=f"vendor-assessment:{a.id}",
                        title=f"Vendor assessment: {v.name} ({a.template_slug})",
                        description=f"Score {a.score}/100, {a.rating} risk. Reviewed by {ctx.user.full_name}. "
                                    f"{body.notes}".strip(),
                        uploaded_by_id=ctx.user.id,
                        valid_until=v.next_review_date or date.today() + timedelta(days=730)))
    audit.record(db, ctx, "vendor.assessment_reviewed", a, vendor=v.name, score=a.score, rating=a.rating)
    db.commit()
    return _assessment_out(a)


@router.post("/vendors/{vendor_id}/documents", status_code=201)
def upload_document(vendor_id: uuid.UUID, db: DB, ctx: WriterCtx, kind: str = Form(...),
                    title: str = Form("", max_length=300), valid_until: date | None = Form(None),
                    file: UploadFile = File(...)):
    v = get_owned(db, Vendor, vendor_id, ctx)
    if kind not in DOC_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown document type")
    key, name, size = storage.save_upload(ctx.org_id, file)
    d = VendorDocument(org_id=ctx.org_id, vendor_id=v.id, kind=kind, title=title.strip() or DOC_KINDS[kind],
                       file_key=key, file_name=name, size_bytes=size, valid_until=valid_until,
                       uploaded_by_id=ctx.user.id)
    if kind in ("iso27001", "soc2"):
        label = "ISO 27001" if kind == "iso27001" else "SOC 2"
        if label not in (v.certifications or []):
            v.certifications = [*(v.certifications or []), label]
    if kind == "dpa":
        v.dpa_signed = True
    db.add(d)
    db.flush()
    audit.record(db, ctx, "vendor.document_uploaded", d, vendor=v.name, kind=kind)
    db.commit()
    return _doc_out(d)


@router.get("/vendors/{vendor_id}/documents/{doc_id}/download")
def download_document(vendor_id: uuid.UUID, doc_id: uuid.UUID, db: DB, ctx: Ctx):
    d = get_owned(db, VendorDocument, doc_id, ctx)
    if d.vendor_id != vendor_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    audit.record(db, ctx, "vendor.document_downloaded", d)
    db.commit()
    return storage.download_response(ctx.org_id, d.file_key, d.file_name)


@router.delete("/vendors/{vendor_id}/documents/{doc_id}", status_code=204)
def delete_document(vendor_id: uuid.UUID, doc_id: uuid.UUID, db: DB, ctx: WriterCtx):
    d = get_owned(db, VendorDocument, doc_id, ctx)
    if d.vendor_id != vendor_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    storage.delete(ctx.org_id, d.file_key)
    audit.record(db, ctx, "vendor.document_deleted", d, title=d.title)
    db.delete(d)
    db.commit()


# ================================================================ public questionnaire (vendor side)


def _public_assessment(db, token: str, for_write: bool = False) -> VendorAssessment:
    ratelimit.enforce("vendor-q", client_ip.get(), 120, 15 * 60)
    set_tenant(db, rls_bypass=True)  # the link token identifies the organisation
    a = db.scalar(select(VendorAssessment).where(VendorAssessment.token_hash == hash_token(token)))
    set_tenant(db, rls_bypass=False)
    if not a or a.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This questionnaire link is invalid or has expired")
    set_tenant(db, org_id=a.org_id)
    if for_write and a.status in ("submitted", "reviewed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This questionnaire has already been submitted")
    return a


@router.get("/public/assessments/{token}")
def public_get(token: str, db: DB):
    a = _public_assessment(db, token)
    t = _template(db, a.template_slug)
    org = db.get(Organization, a.org_id)
    v = db.get(Vendor, a.vendor_id)
    docs = db.scalars(select(VendorDocument).where(VendorDocument.vendor_id == v.id,
                                                   VendorDocument.uploaded_via == "vendor_portal")).all()
    return {"org_name": org.name, "vendor_name": v.name, "title": t.title, "description": t.description,
            "questions": t.questions, "answers": a.answers, "status": a.status, "expires_at": a.expires_at,
            "respondent_name": a.respondent_name, "doc_kinds": DOC_KINDS,
            "documents": [{"kind": d.kind, "title": d.title, "file_name": d.file_name} for d in docs]}


class AnswersIn(BaseModel):
    answers: dict[str, dict] = Field(default_factory=dict)
    respondent_name: str = Field(default="", max_length=200)


def _clean_answers(questions: list[dict], answers: dict[str, dict]) -> dict:
    valid = {q["id"]: q for q in questions}
    out = {}
    for qid, ans in answers.items():
        q = valid.get(qid)
        if not q:
            continue
        value = str(ans.get("answer", ""))[:5000]
        if q.get("type") == "yes_no" and value not in ("yes", "no", "na", ""):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid answer for {qid}")
        out[qid] = {"answer": value, "comment": str(ans.get("comment", ""))[:2000]}
    return out


@router.put("/public/assessments/{token}")
def public_save(token: str, body: AnswersIn, db: DB):
    a = _public_assessment(db, token, for_write=True)
    t = _template(db, a.template_slug)
    a.answers = {**a.answers, **_clean_answers(t.questions, body.answers)}
    a.respondent_name = body.respondent_name.strip() or a.respondent_name
    a.status = "in_progress"
    db.commit()
    return {"status": a.status, "saved": len(a.answers)}


@router.post("/public/assessments/{token}/submit")
def public_submit(token: str, body: AnswersIn, background: BackgroundTasks, db: DB):
    a = _public_assessment(db, token, for_write=True)
    t = _template(db, a.template_slug)
    a.answers = {**a.answers, **_clean_answers(t.questions, body.answers)}
    a.respondent_name = body.respondent_name.strip() or a.respondent_name
    missing = [q["id"] for q in t.questions if q.get("type") == "yes_no" and not (a.answers.get(q["id"]) or {}).get(
        "answer")]
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Answer every yes/no question first ({len(missing)} left)")
    if not a.respondent_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add your name")
    a.score, a.rating, _ = score_answers(t.questions, a.answers)
    a.status, a.submitted_at = "submitted", datetime.now(timezone.utc)
    v = db.get(Vendor, a.vendor_id)
    audit.write(db, org_id=a.org_id, user_id=None, action="vendor.assessment_submitted", entity=a,
                detail={"vendor": v.name, "score": a.score, "by": a.respondent_name})
    owner_email = None
    if v.owner_id:
        from app.models import User

        owner_email = db.scalar(select(User.email).where(User.id == v.owner_id))
    notify.queue(db, a.org_id, key=f"vendor-q:{a.id}:submitted", event="vendor_assessment",
                 to=[owner_email] if owner_email else notify.admin_emails(db, a.org_id),
                 title=f"{v.name} submitted the security questionnaire ({a.score}/100, {a.rating} risk)",
                 link=f"/vendors/{v.id}")
    db.commit()
    return {"status": a.status}


@router.post("/public/assessments/{token}/documents", status_code=201)
def public_upload(token: str, db: DB, kind: str = Form(...), valid_until: date | None = Form(None),
                  file: UploadFile = File(...)):
    a = _public_assessment(db, token, for_write=True)
    ratelimit.enforce("vendor-q-upload", str(a.id), 20, 3600)
    if kind not in DOC_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown document type")
    key, name, size = storage.save_upload(a.org_id, file)
    d = VendorDocument(org_id=a.org_id, vendor_id=a.vendor_id, kind=kind, title=DOC_KINDS[kind], file_key=key,
                       file_name=name, size_bytes=size, valid_until=valid_until, uploaded_via="vendor_portal")
    db.add(d)
    db.commit()
    return {"kind": d.kind, "title": d.title, "file_name": d.file_name}
