"""HR roster: import from CSV exports of any HRMS or from HR connectors."""
import csv
import io
import re
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.base import PersonRecord
from app.models import Person

# Header aliases seen in Keka, Darwinbox, greytHR, Zoho People and spreadsheet exports (normalised, lowercase).
ALIASES = {
    "email": ["email", "work email", "official email", "office email", "email id", "official email id",
              "company email", "email address", "work email address"],
    "full_name": ["name", "full name", "employee name", "display name", "employee full name"],
    "employee_id": ["employee id", "employee number", "emp id", "emp code", "employee code", "emp no", "id"],
    "department": ["department", "dept", "business unit", "team"],
    "title": ["title", "designation", "job title", "position", "role"],
    "manager_email": ["manager email", "reporting manager email", "reports to email", "manager email id",
                      "reporting manager email id", "line manager email"],
    "status": ["status", "employment status", "employee status"],
    "join_date": ["date of joining", "joining date", "doj", "join date", "start date", "hire date"],
    "exit_date": ["date of exit", "exit date", "last working day", "last working date", "lwd", "relieving date",
                  "date of leaving", "termination date", "end date"],
}
EXITED_WORDS = {"exited", "relieved", "resigned", "terminated", "inactive", "left", "separated", "absconded"}
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%m/%d/%Y", "%d.%m.%Y")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RosterError(ValueError):
    pass


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (h or "").lower()).strip()


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    value = value.split("T")[0].split(" 00:00")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def infer_status(raw_status: str, exit_date: date | None, today: date | None = None) -> str:
    today = today or date.today()
    if _norm(raw_status) in EXITED_WORDS or (exit_date is not None and exit_date <= today):
        return "exited"
    return "active"


def parse_csv(content: bytes) -> tuple[list[PersonRecord], list[str]]:
    """Return (records, warnings). Requires an email column."""
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise RosterError("The file is empty or not a CSV")
    columns = {}
    normalised = {_norm(h): h for h in reader.fieldnames}
    for target, aliases in ALIASES.items():
        for a in aliases:
            if a in normalised:
                columns[target] = normalised[a]
                break
    if "email" not in columns:
        raise RosterError("Couldn't find an email column. Add a column named 'Work email' or 'Email'.")
    records, warnings = [], []
    for i, row in enumerate(reader, start=2):
        email = (row.get(columns["email"]) or "").strip().lower()
        if not email:
            continue
        if not EMAIL_RE.match(email):
            warnings.append(f"Row {i}: '{email}' is not a valid email, skipped")
            continue

        def get(k: str, row: dict = row) -> str:
            return (row.get(columns[k]) or "").strip() if k in columns else ""

        exit_date = parse_date(get("exit_date"))
        if get("exit_date") and exit_date is None:
            warnings.append(f"Row {i}: couldn't read exit date '{get('exit_date')}'")
        records.append(PersonRecord(
            email=email, full_name=get("full_name"), employee_id=get("employee_id"), department=get("department"),
            title=get("title"), manager_email=get("manager_email").lower(),
            status=infer_status(get("status"), exit_date), join_date=parse_date(get("join_date")),
            exit_date=exit_date,
        ))
    if not records:
        raise RosterError("No rows with an email address were found")
    return records, warnings[:50]


def upsert_people(db: Session, org_id: uuid.UUID, records: list[PersonRecord], source: str) -> dict:
    existing = {p.email: p for p in db.scalars(select(Person).where(Person.org_id == org_id))}
    created = updated = 0
    for r in records:
        p = existing.get(r.email)
        if p is None:
            p = Person(org_id=org_id, email=r.email)
            existing[r.email] = p
            created += 1
        else:
            updated += 1
        p.source = source
        p.full_name = r.full_name or p.full_name
        p.employee_id = r.employee_id or p.employee_id
        p.department = r.department or p.department
        p.title = r.title or p.title
        p.manager_email = r.manager_email or p.manager_email
        p.status = r.status
        p.join_date = r.join_date or p.join_date
        p.exit_date = r.exit_date
        db.add(p)
    db.flush()
    return {"created": created, "updated": updated}
