"""Security awareness training: built-in courses with quizzes, assignments, completion tracking and imports."""
import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DB, AdminCtx, Ctx
from app.models import Membership, TrainingAssignment, TrainingCompletion, TrainingCourse, User
from app.services import audit
from app.services.people import parse_date

router = APIRouter(prefix="/training", tags=["training"])

DEFAULT_REQUIRED = {"security-essentials", "dpdp-basics", "phishing"}


def ensure_assignments(db, org_id) -> dict[str, TrainingAssignment]:
    existing = {a.course_slug: a for a in db.scalars(select(TrainingAssignment).where(
        TrainingAssignment.org_id == org_id))}
    for c in db.scalars(select(TrainingCourse)):
        if c.slug not in existing:
            a = TrainingAssignment(org_id=org_id, course_slug=c.slug, required=c.slug in DEFAULT_REQUIRED)
            db.add(a)
            existing[c.slug] = a
    db.flush()
    return existing


def completion_status(completion: TrainingCompletion | None, assignment: TrainingAssignment,
                      joined_at: datetime, now: datetime | None = None) -> str:
    """passed | expired | failed | overdue | due | optional"""
    now = now or datetime.now(timezone.utc)
    if completion and completion.passed:
        if completion.completed_at + timedelta(days=30 * assignment.renew_months) > now:
            return "passed"
        return "expired"
    if not assignment.required:
        return "optional"
    if completion and not completion.passed:
        return "failed"
    return "overdue" if joined_at + timedelta(days=assignment.due_days) < now else "due"


def latest_completions(db, org_id) -> dict[tuple[str, str], TrainingCompletion]:
    out: dict[tuple[str, str], TrainingCompletion] = {}
    for c in db.scalars(select(TrainingCompletion).where(TrainingCompletion.org_id == org_id)
                        .order_by(TrainingCompletion.completed_at)):
        key = (c.email, c.course_slug)
        prev = out.get(key)
        if prev is None or c.passed or not prev.passed:
            out[key] = c
    return out


@router.get("/courses")
def courses(db: DB, ctx: Ctx):
    assignments = ensure_assignments(db, ctx.org_id)
    db.commit()
    done = latest_completions(db, ctx.org_id)
    membership = db.scalar(select(Membership).where(Membership.org_id == ctx.org_id,
                                                    Membership.user_id == ctx.user.id))
    out = []
    for c in db.scalars(select(TrainingCourse).order_by(TrainingCourse.title)):
        a = assignments[c.slug]
        comp = done.get((ctx.user.email, c.slug))
        out.append({"slug": c.slug, "title": c.title, "summary": c.summary, "minutes": c.minutes,
                    "required": a.required, "renew_months": a.renew_months, "due_days": a.due_days,
                    "my_status": completion_status(comp, a, membership.created_at),
                    "my_last_completed_at": comp.completed_at if comp else None,
                    "my_score": comp.score if comp else None})
    return out


@router.get("/courses/{slug}")
def course(slug: str, db: DB, ctx: Ctx):
    c = db.scalar(select(TrainingCourse).where(TrainingCourse.slug == slug))
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return {"slug": c.slug, "title": c.title, "summary": c.summary, "minutes": c.minutes, "body_md": c.body_md,
            "pass_mark": c.pass_mark,
            "quiz": [{"q": q["q"], "options": q["options"]} for q in c.quiz]}  # answers stay on the server


class QuizIn(BaseModel):
    answers: list[int] = Field(max_length=50)


@router.post("/courses/{slug}/submit")
def submit(slug: str, body: QuizIn, db: DB, ctx: Ctx):
    c = db.scalar(select(TrainingCourse).where(TrainingCourse.slug == slug))
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    if len(body.answers) != len(c.quiz):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Answer every question")
    correct = [a == q["answer"] for a, q in zip(body.answers, c.quiz, strict=True)]
    score = round(100 * sum(correct) / len(correct))
    passed = score >= c.pass_mark
    db.add(TrainingCompletion(org_id=ctx.org_id, course_slug=slug, user_id=ctx.user.id, email=ctx.user.email,
                              score=score, passed=passed, source="platform"))
    audit.record(db, ctx, "training.completed" if passed else "training.failed", None, course=slug, score=score)
    db.commit()
    return {"score": score, "passed": passed, "pass_mark": c.pass_mark,
            "results": [{"correct": ok, "answer": q["answer"]} for ok, q in zip(correct, c.quiz, strict=True)]}


class AssignmentIn(BaseModel):
    required: bool
    renew_months: int = Field(default=12, ge=1, le=36)
    due_days: int = Field(default=30, ge=1, le=180)


@router.put("/assignments/{slug}")
def update_assignment(slug: str, body: AssignmentIn, db: DB, ctx: AdminCtx):
    a = ensure_assignments(db, ctx.org_id).get(slug)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    a.required, a.renew_months, a.due_days = body.required, body.renew_months, body.due_days
    audit.record(db, ctx, "training.assignment_updated", None, course=slug, required=a.required)
    db.commit()
    return {"slug": slug, **body.model_dump()}


def report_rows(db, org_id) -> tuple[list[dict], list[str]]:
    assignments = ensure_assignments(db, org_id)
    required = sorted(s for s, a in assignments.items() if a.required)
    done = latest_completions(db, org_id)
    rows = []
    for u, m in db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id)
                           .where(Membership.org_id == org_id, Membership.role != "auditor")):
        statuses = {s: completion_status(done.get((u.email, s)), assignments[s], m.created_at) for s in required}
        rows.append({"user_id": u.id, "full_name": u.full_name, "email": u.email, "role": m.role,
                     "courses": statuses, "complete": all(v == "passed" for v in statuses.values())})
    return rows, required


@router.get("/report")
def report(db: DB, ctx: Ctx):
    if not (ctx.is_admin or ctx.role == "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or auditor access required")
    rows, required = report_rows(db, ctx.org_id)
    db.commit()
    total = len(rows)
    complete = sum(r["complete"] for r in rows)
    return {"required_courses": required, "people": sorted(rows, key=lambda r: (r["complete"], r["full_name"])),
            "completion_percent": round(100 * complete / total) if total else 0}


@router.post("/import")
async def import_completions(db: DB, ctx: AdminCtx, file: UploadFile = File(...)):
    """Import completions from another LMS. CSV columns: email, course (slug or title), completed_at[, score]."""
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 2 MB)")
    courses = {c.slug: c for c in db.scalars(select(TrainingCourse))}
    by_title = {c.title.lower(): c.slug for c in courses.values()}
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    cols = {k.strip().lower(): k for k in (reader.fieldnames or [])}
    if not {"email", "course", "completed_at"} <= set(cols):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The CSV needs columns: email, course, completed_at")
    imported, skipped = 0, []
    for i, row in enumerate(reader, start=2):
        email = (row[cols["email"]] or "").strip().lower()
        course_val = (row[cols["course"]] or "").strip()
        slug = course_val if course_val in courses else by_title.get(course_val.lower())
        when = parse_date(row[cols["completed_at"]] or "")
        if not email or "@" not in email or not slug or not when:
            skipped.append(f"Row {i}")
            continue
        score = int(row.get(cols.get("score", ""), "") or 100) if cols.get("score") else 100
        db.add(TrainingCompletion(org_id=ctx.org_id, course_slug=slug, email=email, score=score,
                                  passed=score >= courses[slug].pass_mark, source="import",
                                  completed_at=datetime.combine(when, datetime.min.time(), tzinfo=timezone.utc)))
        imported += 1
    audit.record(db, ctx, "training.imported", None, imported=imported)
    db.commit()
    return {"imported": imported, "skipped": skipped[:50]}
