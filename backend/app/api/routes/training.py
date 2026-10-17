"""Security awareness training: built-in and company courses, role and department assignments, new-joiner due dates,
individual enrollments, certificates, team reporting, roster invitations and imports from another LMS."""
import csv
import io
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DB, AdminCtx, Ctx
from app.models import CustomCourse, Invitation, Membership, TrainingCompletion, User
from app.security import new_token
from app.services import audit, notify
from app.services import training as tr
from app.services.people import parse_date

router = APIRouter(prefix="/training", tags=["training"])


def _me(db, ctx) -> tr.Learner:
    for p in tr.learners(db, ctx.org_id):
        if p.user_id == ctx.user.id:
            return p
    m = db.scalar(select(Membership).where(Membership.org_id == ctx.org_id, Membership.user_id == ctx.user.id))
    return tr.Learner(ctx.user.email.lower(), ctx.user.full_name, "", m.created_at.date(), ctx.user.id, m.role)


# ================================================================ learner


@router.get("/courses")
def courses(db: DB, ctx: Ctx):
    assignments = tr.ensure_assignments(db, ctx.org_id)
    db.commit()
    cat = tr.catalog(db, ctx.org_id, include_drafts=ctx.is_admin)
    plan = tr.person_plan(db, ctx.org_id, _me(db, ctx), assignments)
    out = []
    for slug, c in cat.items():
        a, p = assignments.get(slug), plan.get(slug, {})
        item = {"slug": slug, "title": c["title"], "summary": c["summary"], "minutes": c["minutes"],
                "category": c["category"], "audience": c["audience"], "source": c["source"],
                "published": c["published"], "has_scenarios": bool(c["scenarios"]), "has_video": bool(c["video_url"]),
                "questions": len(c["quiz"]),
                "required": bool(p.get("required")), "my_status": p.get("status", "optional"),
                "my_due": p.get("due"), "my_reason": p.get("reason", ""),
                "my_last_completed_at": p.get("completed_at"), "my_score": p.get("score"),
                "has_certificate": bool(p.get("completion_id"))}
        if a is not None:
            item.update({"assignment": {"required": a.required, "renew_months": a.renew_months,
                                        "due_days": a.due_days, "departments": a.departments or []}})
        out.append(item)
    return out


@router.get("/courses/{slug}")
def course(slug: str, db: DB, ctx: Ctx):
    c = tr.get_course(db, ctx.org_id, slug, include_drafts=ctx.is_admin)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return {"slug": slug, "title": c["title"], "summary": c["summary"], "minutes": c["minutes"],
            "body_md": c["body_md"], "pass_mark": c["pass_mark"], "video_url": c["video_url"],
            "scenarios": c["scenarios"], "category": c["category"],
            "quiz": [{"q": q["q"], "options": q["options"]} for q in c["quiz"]]}  # answers stay on the server


class QuizIn(BaseModel):
    answers: list[int] = Field(max_length=50)


@router.post("/courses/{slug}/submit")
def submit(slug: str, body: QuizIn, db: DB, ctx: Ctx):
    c = tr.get_course(db, ctx.org_id, slug)
    if not c or not c["quiz"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    if len(body.answers) != len(c["quiz"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Answer every question")
    correct = [a == q["answer"] for a, q in zip(body.answers, c["quiz"], strict=True)]
    score = round(100 * sum(correct) / len(correct))
    passed = score >= c["pass_mark"]
    comp = TrainingCompletion(org_id=ctx.org_id, course_slug=slug, user_id=ctx.user.id, email=ctx.user.email.lower(),
                              score=score, passed=passed, source="platform")
    db.add(comp)
    db.flush()
    audit.record(db, ctx, "training.completed" if passed else "training.failed", None, course=slug, score=score)
    db.commit()
    return {"score": score, "passed": passed, "pass_mark": c["pass_mark"], "certificate": passed,
            "results": [{"correct": ok, "answer": q["answer"], "explain": q.get("explain", "")}
                        for ok, q in zip(correct, c["quiz"], strict=True)]}


@router.get("/courses/{slug}/certificate")
def certificate(slug: str, db: DB, ctx: Ctx):
    c = tr.get_course(db, ctx.org_id, slug)
    plan = tr.person_plan(db, ctx.org_id, _me(db, ctx)).get(slug)
    if not c or not plan or not plan.get("completion_id"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pass the course to get a certificate")
    a = tr.ensure_assignments(db, ctx.org_id)[slug]
    done = plan["completed_at"]
    return {"certificate_id": str(plan["completion_id"]).split("-")[0].upper(), "name": ctx.user.full_name,
            "course": c["title"], "minutes": c["minutes"], "score": plan["score"], "completed_at": done,
            "valid_until": (done + timedelta(days=30 * a.renew_months)).date(), "org_name": ctx.org.name}


# ================================================================ admin: assignments and reporting


class AssignmentIn(BaseModel):
    required: bool
    renew_months: int = Field(default=12, ge=1, le=36)
    due_days: int = Field(default=30, ge=1, le=180)
    departments: list[str] = Field(default_factory=list, max_length=50)


@router.put("/assignments/{slug}")
def update_assignment(slug: str, body: AssignmentIn, db: DB, ctx: AdminCtx):
    a = tr.ensure_assignments(db, ctx.org_id).get(slug)
    if not a:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    if body.required and not a.required:
        a.required_since = date.today()
    a.required, a.renew_months, a.due_days = body.required, body.renew_months, body.due_days
    a.departments = sorted({d.strip()[:200] for d in body.departments if d.strip()})
    audit.record(db, ctx, "training.assignment_updated", None, course=slug, required=a.required,
                 departments=a.departments)
    db.commit()
    return {"slug": slug, **body.model_dump(), "departments": a.departments}


@router.get("/departments")
def departments(db: DB, ctx: Ctx):
    return tr.departments(db, ctx.org_id)


def _report_access(ctx):
    if not (ctx.is_admin or ctx.role == "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or auditor access required")


@router.get("/report")
def report(db: DB, ctx: Ctx):
    _report_access(ctx)
    r = tr.report(db, ctx.org_id)
    db.commit()
    order = {"overdue": 0, "expired": 0, "failed": 0, "due": 1, "passed": 2}
    r["people"].sort(key=lambda p: (p["complete"], min((order.get(s, 3) for s in p["courses"].values()), default=3),
                                    p["full_name"].lower()))
    cat = tr.catalog(db, ctx.org_id)
    r["course_titles"] = {s: cat[s]["title"] for s in r["required_courses"] if s in cat}
    return r


@router.get("/report.csv")
def report_csv(db: DB, ctx: Ctx):
    """Evidence for auditors: who must take which course, status, due date and last completion."""
    _report_access(ctx)
    r = tr.report(db, ctx.org_id)
    done = tr.latest_completions(db, ctx.org_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Email", "Department", "Has account", "Course", "Status", "Due", "Last completed", "Score"])
    for p in r["people"]:
        for slug, st in p["courses"].items():
            comp = done.get((p["email"], slug))
            w.writerow([_csv_safe(p["full_name"]), p["email"], _csv_safe(p["department"]),
                        "yes" if p["has_account"] else "no", slug, st, p["due"].get(slug) or "",
                        comp.completed_at.date() if comp else "", comp.score if comp else ""])
    audit.record(db, ctx, "training.report_exported", None)
    db.commit()
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="training-report-{date.today()}.csv"'})


def _csv_safe(v: str) -> str:
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


@router.post("/invite-roster")
def invite_roster(db: DB, ctx: AdminCtx):
    """Invite active people from the HR roster who don't have an account yet, so they can take their training."""
    if not ctx.user.email_verified_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Confirm your own email address before inviting others")
    pending = {e.lower() for e in db.scalars(select(Invitation.email).where(
        Invitation.org_id == ctx.org_id, Invitation.accepted_at.is_(None),
        Invitation.expires_at > datetime.now(timezone.utc)))}
    targets = [p for p in tr.learners(db, ctx.org_id) if not p.has_account and p.email not in pending][:500]
    base = get_settings().public_url.rstrip("/")
    for p in targets:
        if db.scalar(select(User).where(func.lower(User.email) == p.email)) and db.scalar(
                select(Membership).join(User, User.id == Membership.user_id).where(
                    Membership.org_id == ctx.org_id, func.lower(User.email) == p.email)):
            continue
        token, token_hash = new_token()
        db.add(Invitation(org_id=ctx.org_id, email=p.email, role="member", token_hash=token_hash,
                          invited_by_id=ctx.user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=14)))
        notify.send_email_safely([p.email], f"Security training at {ctx.org.name}",
                                 f"Hi {p.full_name.split()[0] if p.full_name else ''},\n\n{ctx.org.name} uses "
                                 f"{get_settings().app_name} for security awareness training. Create your account "
                                 f"to see the short courses assigned to you:\n\n{base}/invite/{token}\n\n"
                                 "The invitation is valid for 14 days.")
    audit.record(db, ctx, "training.roster_invited", None, count=len(targets))
    db.commit()
    return {"invited": len(targets)}


@router.post("/import")
async def import_completions(db: DB, ctx: AdminCtx, file: UploadFile = File(...)):
    """Import completions from another LMS. CSV columns: email, course (slug or title), completed_at[, score]."""
    content = await file.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File too large (max 2 MB)")
    courses = tr.catalog(db, ctx.org_id, include_drafts=True)
    by_title = {c["title"].lower(): s for s, c in courses.items()}
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
        try:
            score = int(row.get(cols.get("score", ""), "") or 100) if cols.get("score") else 100
        except ValueError:
            skipped.append(f"Row {i}")
            continue
        db.add(TrainingCompletion(org_id=ctx.org_id, course_slug=slug, email=email, score=max(0, min(100, score)),
                                  passed=score >= courses[slug]["pass_mark"], source="import",
                                  completed_at=datetime.combine(when, datetime.min.time(), tzinfo=timezone.utc)))
        imported += 1
    audit.record(db, ctx, "training.imported", None, imported=imported)
    db.commit()
    return {"imported": imported, "skipped": skipped[:50]}


# ================================================================ admin: company courses


class QuizItem(BaseModel):
    q: str = Field(min_length=3, max_length=500)
    options: list[str] = Field(min_length=2, max_length=6)
    answer: int = Field(ge=0)
    explain: str = Field(default="", max_length=1000)

    @field_validator("options")
    @classmethod
    def opts(cls, v: list[str]) -> list[str]:
        v = [o.strip()[:300] for o in v]
        if any(not o for o in v):
            raise ValueError("options can't be empty")
        return v


class CourseIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    summary: str = Field(default="", max_length=1000)
    minutes: int = Field(default=10, ge=1, le=180)
    body_md: str = Field(default="", max_length=200_000)
    video_url: str = Field(default="", max_length=500)
    quiz: list[QuizItem] = Field(default_factory=list, max_length=30)
    pass_mark: int = Field(default=80, ge=0, le=100)
    control_codes: list[str] = Field(default_factory=lambda: ["HR-03"], max_length=20)
    published: bool = False

    @field_validator("video_url")
    @classmethod
    def https_only(cls, v: str) -> str:
        v = v.strip()
        if v and not re.match(r"^https://", v, re.I):
            raise ValueError("use an https:// link")
        return v


def _check_quiz(body: CourseIn) -> None:
    for i, q in enumerate(body.quiz, start=1):
        if q.answer >= len(q.options):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Question {i}: pick which option is correct")
    if body.published and not body.quiz:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Add at least one quiz question before publishing")


def _custom(db, ctx, slug: str) -> CustomCourse:
    c = db.scalar(select(CustomCourse).where(CustomCourse.org_id == ctx.org_id, CustomCourse.slug == slug))
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return c


def _custom_out(c: CustomCourse) -> dict:
    return {"slug": c.slug, "title": c.title, "summary": c.summary, "minutes": c.minutes, "body_md": c.body_md,
            "video_url": c.video_url, "quiz": c.quiz, "pass_mark": c.pass_mark, "control_codes": c.control_codes,
            "published": c.published, "updated_at": c.updated_at}


@router.post("/custom", status_code=201)
def create_course(body: CourseIn, db: DB, ctx: AdminCtx):
    _check_quiz(body)
    c = CustomCourse(org_id=ctx.org_id, slug=f"org-{uuid.uuid4().hex[:10]}", created_by_id=ctx.user.id,
                     **{**body.model_dump(), "quiz": [q.model_dump() for q in body.quiz]})
    db.add(c)
    db.flush()
    audit.record(db, ctx, "training.course_created", c, title=c.title)
    db.commit()
    return _custom_out(c)


@router.get("/custom/{slug}")
def get_custom(slug: str, db: DB, ctx: AdminCtx):
    return _custom_out(_custom(db, ctx, slug))


@router.put("/custom/{slug}")
def update_course(slug: str, body: CourseIn, db: DB, ctx: AdminCtx):
    c = _custom(db, ctx, slug)
    _check_quiz(body)
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    c.quiz = [q.model_dump() for q in body.quiz]
    audit.record(db, ctx, "training.course_updated", c, published=c.published)
    db.commit()
    return _custom_out(c)


@router.delete("/custom/{slug}", status_code=204)
def delete_course(slug: str, db: DB, ctx: AdminCtx):
    c = _custom(db, ctx, slug)
    audit.record(db, ctx, "training.course_deleted", c, title=c.title)
    db.delete(c)  # completion records stay as history
    db.commit()
