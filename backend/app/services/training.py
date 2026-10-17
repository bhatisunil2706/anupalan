"""Training engine: the course catalogue (built-in + company courses), who must take what, due dates and progress.

A course is required of a person when its assignment is required and the person is in one of the assignment's
departments (or the assignment covers everyone), or when the person has an individual enrollment (for example after
clicking a phishing simulation). The due date counts from the later of the person's joining date and the date the
course was made required, so new joiners get the same window as everyone else.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CustomCourse,
    Membership,
    Person,
    TrainingAssignment,
    TrainingCompletion,
    TrainingCourse,
    TrainingEnrollment,
    User,
)

DEFAULT_REQUIRED = {"security-essentials", "dpdp-basics", "phishing"}
# Role-based defaults: when a company has these departments in its HR roster, these courses are suggested for them.
ROLE_COURSES = {"secure-development": ["engineering", "technology", "product", "development", "it"],
                "payment-fraud": ["finance", "accounts", "payroll", "procurement"],
                "privacy-support": ["support", "customer", "operations", "success", "service"]}


@dataclass
class Learner:
    email: str
    full_name: str
    department: str
    start: date
    user_id: uuid.UUID | None
    role: str
    manager_email: str = ""

    @property
    def has_account(self) -> bool:
        return self.user_id is not None


def _course_dict(c, source: str) -> dict:
    built_in = source == "built_in"
    return {"slug": c.slug, "title": c.title, "summary": c.summary, "minutes": c.minutes, "body_md": c.body_md,
            "quiz": c.quiz or [], "pass_mark": c.pass_mark, "control_codes": c.control_codes or [], "source": source,
            "category": c.category if built_in else "Your courses",
            "audience": c.audience if built_in else "Set by your company",
            "scenarios": (c.scenarios or []) if built_in else [],
            "video_url": "" if built_in else c.video_url,
            "published": True if built_in else c.published,
            "order": c.order if built_in else 50}


def catalog(db: Session, org_id: uuid.UUID, include_drafts: bool = False) -> dict[str, dict]:
    out = {c.slug: _course_dict(c, "built_in") for c in db.scalars(select(TrainingCourse))}
    for c in db.scalars(select(CustomCourse).where(CustomCourse.org_id == org_id)):
        if c.published or include_drafts:
            out[c.slug] = _course_dict(c, "custom")
    return dict(sorted(out.items(), key=lambda kv: (kv[1]["order"], kv[1]["title"])))


def get_course(db: Session, org_id: uuid.UUID, slug: str, include_drafts: bool = False) -> dict | None:
    return catalog(db, org_id, include_drafts).get(slug)


def ensure_assignments(db: Session, org_id: uuid.UUID) -> dict[str, TrainingAssignment]:
    existing = {a.course_slug: a for a in db.scalars(select(TrainingAssignment).where(
        TrainingAssignment.org_id == org_id))}
    for slug in catalog(db, org_id):
        if slug not in existing:
            a = TrainingAssignment(org_id=org_id, course_slug=slug, required=slug in DEFAULT_REQUIRED,
                                   renew_months=12, due_days=30, departments=[], required_since=date.today())
            if slug in ROLE_COURSES:
                depts = departments(db, org_id)
                matched = [d for d in depts if any(k in d.lower() for k in ROLE_COURSES[slug])]
                if matched:
                    a.required, a.departments = True, matched
            db.add(a)
            existing[slug] = a
    db.flush()
    return existing


def departments(db: Session, org_id: uuid.UUID) -> list[str]:
    return sorted({d for d in db.scalars(select(Person.department).where(
        Person.org_id == org_id, Person.status == "active", Person.department != "")) if d})


def learners(db: Session, org_id: uuid.UUID) -> list[Learner]:
    """Everyone who should be trained: workspace members (except auditors) plus active people in the HR roster."""
    roster = {p.email.lower(): p for p in db.scalars(select(Person).where(Person.org_id == org_id))}
    out: dict[str, Learner] = {}
    for u, m in db.execute(select(User, Membership).join(Membership, Membership.user_id == User.id)
                           .where(Membership.org_id == org_id, Membership.role != "auditor")):
        p = roster.get(u.email.lower())
        if p and p.status == "exited":
            continue
        start = (p.join_date if p and p.join_date else m.created_at.date())
        out[u.email.lower()] = Learner(u.email.lower(), u.full_name, p.department if p else "", start, u.id, m.role,
                                       p.manager_email if p else "")
    for email, p in roster.items():
        if email in out or p.status != "active":
            continue
        out[email] = Learner(email, p.full_name or email, p.department, p.join_date or p.created_at.date(), None,
                             "not invited", p.manager_email)
    return sorted(out.values(), key=lambda learner: learner.full_name.lower())


def latest_completions(db: Session, org_id: uuid.UUID) -> dict[tuple[str, str], TrainingCompletion]:
    out: dict[tuple[str, str], TrainingCompletion] = {}
    for c in db.scalars(select(TrainingCompletion).where(TrainingCompletion.org_id == org_id)
                        .order_by(TrainingCompletion.completed_at)):
        key = (c.email.lower(), c.course_slug)
        prev = out.get(key)
        if prev is None or c.passed or not prev.passed:
            out[key] = c
    return out


def applies(a: TrainingAssignment, learner: Learner) -> bool:
    return a.required and (not a.departments or learner.department in a.departments)


def due_date(a: TrainingAssignment, learner: Learner) -> date:
    assigned = a.required_since or (a.created_at or datetime.now(timezone.utc)).date()
    return max(learner.start, assigned) + timedelta(days=a.due_days)


def status_for(completion: TrainingCompletion | None, renew_months: int, required: bool, due: date | None,
               today: date | None = None) -> str:
    """passed | expired | failed | overdue | due | optional"""
    today = today or date.today()
    if completion and completion.passed:
        if completion.completed_at.date() + timedelta(days=30 * renew_months) > today:
            return "passed"
        return "expired" if required else "optional"
    if not required:
        return "optional"
    if completion and not completion.passed:
        return "failed"
    return "overdue" if due and due < today else "due"


def person_plan(db: Session, org_id: uuid.UUID, learner: Learner, assignments=None, enrollments=None,
                done=None, today: date | None = None) -> dict[str, dict]:
    """slug -> {required, status, due, reason} for one person."""
    assignments = assignments if assignments is not None else ensure_assignments(db, org_id)
    if enrollments is None:
        enrollments = {(e.email.lower(), e.course_slug): e for e in db.scalars(
            select(TrainingEnrollment).where(TrainingEnrollment.org_id == org_id))}
    done = done if done is not None else latest_completions(db, org_id)
    plan = {}
    for slug, a in assignments.items():
        enr = enrollments.get((learner.email, slug))
        required = applies(a, learner) or enr is not None
        due = None
        if enr is not None and not applies(a, learner):
            due = enr.due_date
        elif required:
            due = due_date(a, learner)
        comp = done.get((learner.email, slug))
        # An enrollment after a phishing click needs a completion newer than the enrollment.
        if enr is not None and comp and comp.passed and comp.completed_at < enr.created_at:
            comp = None
        state = status_for(comp, a.renew_months, required, due, today)
        plan[slug] = {"required": required, "due": due, "status": state,
                      "reason": enr.reason if enr else ("Department" if a.departments and required else ""),
                      "completed_at": comp.completed_at if comp else None, "score": comp.score if comp else None,
                      "completion_id": comp.id if comp and comp.passed else None}
    return plan


def report(db: Session, org_id: uuid.UUID, today: date | None = None) -> dict:
    assignments = ensure_assignments(db, org_id)
    cat = catalog(db, org_id)
    enrollments = {(e.email.lower(), e.course_slug): e for e in db.scalars(
        select(TrainingEnrollment).where(TrainingEnrollment.org_id == org_id))}
    done = latest_completions(db, org_id)
    rows = []
    for learner in learners(db, org_id):
        plan = person_plan(db, org_id, learner, assignments, enrollments, done, today)
        req = {s: p for s, p in plan.items() if p["required"] and s in cat}
        rows.append({"user_id": learner.user_id, "full_name": learner.full_name, "email": learner.email,
                     "department": learner.department, "role": learner.role, "has_account": learner.has_account,
                     "manager_email": learner.manager_email,
                     "courses": {s: p["status"] for s, p in req.items()},
                     "due": {s: p["due"] for s, p in req.items()},
                     "complete": all(p["status"] == "passed" for p in req.values())})
    required_courses = sorted({s for r in rows for s in r["courses"]},
                              key=lambda s: cat[s]["order"] if s in cat else 99)
    by_dept: dict[str, list[dict]] = {}
    for r in rows:
        by_dept.setdefault(r["department"] or "No department", []).append(r)
    dept_stats = [{"department": d, "people": len(rs), "complete": sum(r["complete"] for r in rs),
                   "percent": round(100 * sum(r["complete"] for r in rs) / len(rs)),
                   "overdue": sum(1 for r in rs if any(st in ("overdue", "expired", "failed")
                                                       for st in r["courses"].values()))}
                  for d, rs in sorted(by_dept.items())]
    with_account = [r for r in rows if r["has_account"]]
    return {"people": rows, "required_courses": required_courses, "departments": dept_stats,
            "completion_percent": round(100 * sum(r["complete"] for r in rows) / len(rows)) if rows else 0,
            "with_account_percent": round(100 * sum(r["complete"] for r in with_account) / len(with_account))
            if with_account else 0,
            "not_invited": sum(1 for r in rows if not r["has_account"])}


def report_rows(db: Session, org_id: uuid.UUID) -> tuple[list[dict], list[str]]:
    """Back-compatible view used by reminders and the HR-03 check: people with accounts only."""
    r = report(db, org_id)
    return [p for p in r["people"] if p["has_account"]], r["required_courses"]


def enroll(db: Session, org_id: uuid.UUID, email: str, course_slug: str, reason: str, days: int = 14) -> None:
    email = email.lower()
    e = db.scalar(select(TrainingEnrollment).where(TrainingEnrollment.org_id == org_id,
                                                   TrainingEnrollment.course_slug == course_slug,
                                                   TrainingEnrollment.email == email))
    due = date.today() + timedelta(days=days)
    if e:
        e.reason, e.due_date = reason[:200], due
        e.created_at = datetime.now(timezone.utc)  # needs a fresh completion after this enrollment
    else:
        db.add(TrainingEnrollment(org_id=org_id, course_slug=course_slug, email=email, reason=reason[:200],
                                  due_date=due))
