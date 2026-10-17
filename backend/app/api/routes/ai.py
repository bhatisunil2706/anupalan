"""AI assistant endpoints. Jobs run in the worker; people review every output before it is used."""
import csv
import io
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, Ctx, WriterCtx, get_owned
from app.models import AiJob, Policy
from app.services import audit
from app.services.ai import MAX_QUESTIONS

router = APIRouter(tags=["ai"])


def _used_today(db, org_id) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    return db.scalar(select(func.count(AiJob.id)).where(AiJob.org_id == org_id, AiJob.created_at >= since,
                                                        AiJob.kind != "evidence_check")) or 0


@router.get("/ai/status")
def ai_status(db: DB, ctx: Ctx):
    s = get_settings()
    return {"enabled": ctx.org.ai_enabled, "available": bool(s.anthropic_api_key), "model": s.ai_model,
            "used_24h": _used_today(db, ctx.org_id), "limit_24h": s.ai_daily_jobs_per_org,
            "can_toggle": ctx.role == "owner", "evidence_checks": ctx.org.ai_evidence_checks}


class ToggleIn(BaseModel):
    enabled: bool
    acknowledge_data_sharing: bool = False


@router.put("/org/ai")
def toggle(body: ToggleIn, db: DB, ctx: Ctx):
    if ctx.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can turn the AI assistant on or off")
    if body.enabled and not get_settings().anthropic_api_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The AI assistant isn't configured on this server")
    if body.enabled and not body.acknowledge_data_sharing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Confirm that policy and control text may be sent to the AI provider")
    ctx.org.ai_enabled = body.enabled
    if not body.enabled:
        ctx.org.ai_evidence_checks = False
    audit.record(db, ctx, "ai.enabled" if body.enabled else "ai.disabled", ctx.org)
    db.commit()
    return {"enabled": ctx.org.ai_enabled}


class EvidenceSettingsIn(BaseModel):
    require_evidence_review: bool | None = None
    ai_evidence_checks: bool | None = None
    acknowledge_file_sharing: bool = False


@router.put("/org/evidence-settings")
def evidence_settings(body: EvidenceSettingsIn, db: DB, ctx: Ctx):
    """Second-person review of uploaded evidence (admins), and AI evidence checks (owner only, explicit consent,
    because evidence files are sent to the AI provider)."""
    org = ctx.org
    if body.require_evidence_review is not None:
        if not ctx.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
        org.require_evidence_review = body.require_evidence_review
        audit.record(db, ctx, "evidence.review_required" if body.require_evidence_review
                     else "evidence.review_not_required", org)
    if body.ai_evidence_checks is not None:
        if ctx.role != "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can turn AI evidence checks on or off")
        if body.ai_evidence_checks:
            if not org.ai_enabled:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turn on the AI assistant first")
            if not body.acknowledge_file_sharing:
                raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                    "Confirm that evidence files may be sent to the AI provider for checking")
        org.ai_evidence_checks = body.ai_evidence_checks
        audit.record(db, ctx, "ai.evidence_checks_enabled" if body.ai_evidence_checks
                     else "ai.evidence_checks_disabled", org)
    db.commit()
    return {"require_evidence_review": org.require_evidence_review, "ai_evidence_checks": org.ai_evidence_checks}


class Question(BaseModel):
    id: str = Field(max_length=50)
    text: str = Field(max_length=2000)


class JobIn(BaseModel):
    kind: Literal["policy_draft", "gap_analysis", "questionnaire"]
    title: str = Field(default="", max_length=300)
    topic: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=4000)
    control_codes: list[str] = Field(default_factory=list, max_length=20)
    framework_code: str = Field(default="", max_length=50)
    questions: list[Question] = Field(default_factory=list, max_length=MAX_QUESTIONS)


def _job_out(j: AiJob, full: bool = True) -> dict:
    out = {"id": j.id, "kind": j.kind, "title": j.title, "status": j.status, "error": j.error,
           "created_at": j.created_at, "finished_at": j.finished_at,
           "created_by": j.created_by.full_name if j.created_by else None}
    if full:
        out |= {"input": j.input, "output": j.output, "tokens_in": j.tokens_in, "tokens_out": j.tokens_out}
    return out


@router.post("/ai/jobs", status_code=201)
def create_job(body: JobIn, db: DB, ctx: WriterCtx):
    s = get_settings()
    if not (ctx.org.ai_enabled and s.anthropic_api_key):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The AI assistant is turned off for your organisation")
    if _used_today(db, ctx.org_id) >= s.ai_daily_jobs_per_org:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Daily AI limit reached. Try again tomorrow.")
    if body.kind == "policy_draft" and not body.topic.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say what the policy is about")
    if body.kind == "gap_analysis" and not body.framework_code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a framework")
    if body.kind == "questionnaire" and not body.questions:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add at least one question")
    data = body.model_dump(exclude={"kind", "title"})
    title = body.title or {"policy_draft": f"Policy draft: {body.topic}",
                           "gap_analysis": f"Gap analysis: {body.framework_code}",
                           "questionnaire": f"Questionnaire ({len(body.questions)} questions)"}[body.kind]
    j = AiJob(org_id=ctx.org_id, kind=body.kind, title=title[:300], input=data, created_by_id=ctx.user.id)
    db.add(j)
    db.flush()
    audit.record(db, ctx, "ai.job_created", j, kind=j.kind)
    db.commit()
    return _job_out(j)


@router.get("/ai/jobs")
def list_jobs(db: DB, ctx: Ctx):
    rows = db.scalars(select(AiJob).where(AiJob.org_id == ctx.org_id, AiJob.kind != "evidence_check")
                      .order_by(AiJob.created_at.desc()).limit(100))
    return [_job_out(j, full=False) for j in rows]


@router.get("/ai/jobs/{job_id}")
def get_job(job_id: uuid.UUID, db: DB, ctx: Ctx):
    return _job_out(get_owned(db, AiJob, job_id, ctx))


@router.post("/ai/questionnaire/parse")
async def parse_questionnaire(db: DB, ctx: WriterCtx, file: UploadFile = File(...)):
    """Read questions from a CSV or XLSX: the first column whose header looks like 'question', else column A."""
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 5 MB)")
    name = (file.filename or "").lower()
    rows: list[list[str]] = []
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        if not content.startswith(b"PK"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That isn't a valid .xlsx file")
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001 - any parse failure is a bad upload
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Couldn't read that spreadsheet") from e
        for row in wb.worksheets[0].iter_rows(values_only=True, max_row=2000):
            rows.append(["" if v is None else str(v) for v in row])
    elif name.endswith(".csv") or name.endswith(".txt"):
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))[:2000]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Upload a .csv or .xlsx file")
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return {"questions": []}
    header = [c.strip().lower() for c in rows[0]]
    col = next((i for i, h in enumerate(header) if "question" in h), None)
    data = rows[1:] if col is not None else rows
    col = col or 0
    id_col = next((i for i, h in enumerate(header) if h in ("id", "#", "no", "no.", "ref")), None)
    questions = []
    for n, r in enumerate(data, start=1):
        text = r[col].strip() if col < len(r) else ""
        if len(text) < 8:
            continue
        qid = (r[id_col].strip() if id_col is not None and id_col < len(r) else "") or str(n)
        questions.append({"id": qid[:50], "text": text[:2000]})
    return {"questions": questions[:MAX_QUESTIONS], "truncated": len(questions) > MAX_QUESTIONS}


class AnswerEdit(BaseModel):
    id: str
    answer: Literal["yes", "no", "partial", "unknown"]
    response: str = Field(max_length=5000)
    reviewed: bool = True


@router.put("/ai/jobs/{job_id}/answers")
def edit_answers(job_id: uuid.UUID, body: list[AnswerEdit], db: DB, ctx: WriterCtx):
    j = get_owned(db, AiJob, job_id, ctx)
    if j.kind != "questionnaire" or j.status != "done":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only finished questionnaires can be edited")
    edits = {e.id: e for e in body}
    answers = []
    for a in j.output.get("answers", []):
        e = edits.get(a["id"])
        answers.append({**a, "answer": e.answer, "response": e.response, "reviewed": e.reviewed} if e else a)
    j.output = {**j.output, "answers": answers}
    db.commit()
    return _job_out(j)


@router.get("/ai/jobs/{job_id}/export.xlsx")
def export_answers(job_id: uuid.UUID, db: DB, ctx: Ctx):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    from app.api.routes.auditor import _xlsx_cell

    j = get_owned(db, AiJob, job_id, ctx)
    if j.kind != "questionnaire" or j.status != "done":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to export yet")
    wb = Workbook()
    ws = wb.active
    ws.title = "Answers"
    ws.append(["ID", "Question", "Answer", "Response", "Confidence", "Reviewed", "Sources"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for a in j.output.get("answers", []):
        ws.append([_xlsx_cell(x) for x in (a["id"], a["question"], a["answer"].title(), a["response"],
                                             a["confidence"], "Yes" if a.get("reviewed") else "No",
                                             "; ".join(s["source"] for s in a.get("sources", [])))])
    for col, w in zip("ABCDEFG", (8, 60, 10, 70, 11, 9, 40), strict=True):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="questionnaire-answers.xlsx"',
                             "Cache-Control": "no-store"})


@router.post("/ai/jobs/{job_id}/save-policy", status_code=201)
def save_policy(job_id: uuid.UUID, db: DB, ctx: WriterCtx):
    j = get_owned(db, AiJob, job_id, ctx)
    if j.kind != "policy_draft" or j.status != "done":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only finished policy drafts can be saved")
    p = Policy(org_id=ctx.org_id, slug="ai-" + uuid.uuid4().hex[:8], title=j.output["title"],
               body_md=j.output["body_md"], control_codes=j.output.get("control_codes", []), owner_id=ctx.user.id)
    db.add(p)
    db.flush()
    audit.record(db, ctx, "policy.created", p, from_ai_job=str(j.id))
    db.commit()
    return {"policy_id": p.id}
