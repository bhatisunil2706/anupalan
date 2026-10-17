"""Vendor questionnaires: built-in and company templates, Excel/CSV import and export, links and reminders."""
import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CustomQuestionnaire, Organization, QuestionnaireTemplate, Vendor, VendorAssessment
from app.security import new_token
from app.services import notify
from app.services.content import ContentError, validate_questions

MAX_QUESTIONS = 400
IMPORT_MAX_BYTES = 5 * 1024 * 1024
TYPE_ALIASES = {"yes/no": "yes_no", "yesno": "yes_no", "yes_no": "yes_no", "boolean": "yes_no", "y/n": "yes_no",
                "text": "text", "free text": "text", "comment": "text", "choice": "choice", "select": "choice",
                "multiple choice": "choice", "dropdown": "choice"}


@dataclass
class Template:
    slug: str
    title: str
    description: str
    questions: list[dict]
    kind: str = "core"
    recommended_for: list[str] = field(default_factory=list)
    source: str = "built_in"  # built_in | custom
    order: int = 100
    updated_at: datetime | None = None
    based_on: str = ""

    def summary(self) -> dict:
        sections = list(dict.fromkeys(q.get("section", "") for q in self.questions))
        return {"slug": self.slug, "title": self.title, "description": self.description,
                "questions": len(self.questions), "scored": sum(1 for q in self.questions
                                                                  if q.get("type") == "yes_no" and q.get("weight")),
                "sections": sections, "kind": self.kind, "recommended_for": self.recommended_for,
                "source": self.source, "updated_at": self.updated_at, "based_on": self.based_on}


def _from_builtin(t: QuestionnaireTemplate) -> Template:
    return Template(t.slug, t.title, t.description, t.questions, t.kind, list(t.recommended_for or []),
                    "built_in", t.order)


def _from_custom(c: CustomQuestionnaire) -> Template:
    return Template(c.slug, c.title, c.description, c.questions, "custom", [], "custom", 50, c.updated_at,
                    c.based_on)


def get_template(db: Session, org_id: uuid.UUID, slug: str) -> Template | None:
    if slug.startswith("org-"):
        c = db.scalar(select(CustomQuestionnaire).where(CustomQuestionnaire.org_id == org_id,
                                                        CustomQuestionnaire.slug == slug))
        return _from_custom(c) if c else None
    t = db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.slug == slug))
    return _from_builtin(t) if t else None


def list_templates(db: Session, org_id: uuid.UUID) -> list[Template]:
    built = [_from_builtin(t) for t in db.scalars(select(QuestionnaireTemplate))]
    custom = [_from_custom(c) for c in db.scalars(select(CustomQuestionnaire)
                                                  .where(CustomQuestionnaire.org_id == org_id))]
    return sorted(built, key=lambda t: (t.order, t.title)) + sorted(custom, key=lambda t: t.title.lower())


def questions_of(db: Session, a: VendorAssessment) -> list[dict]:
    """The questions the vendor was sent (snapshot), falling back to the template for older assessments."""
    if a.questions:
        return a.questions
    t = get_template(db, a.org_id, a.template_slug)
    return t.questions if t else []


def clean_questions(raw: list[dict]) -> list[dict]:
    """Normalise questions coming from the editor or an import, then validate."""
    if len(raw) > MAX_QUESTIONS:
        raise ContentError(f"Questionnaires can have up to {MAX_QUESTIONS} questions")
    out, seen = [], set()
    for i, q in enumerate(raw, start=1):
        text = str(q.get("text", "")).strip()[:1000]
        if not text:
            continue
        qtype = TYPE_ALIASES.get(str(q.get("type", "yes_no")).strip().lower(), "")
        if not qtype:
            raise ContentError(f"Question {i}: type must be yes/no, text or choice")
        qid = re.sub(r"[^a-z0-9_-]", "", str(q.get("id", "")).strip().lower())[:40] or f"q-{i}"
        while qid in seen:
            qid = f"{qid}-{i}"
        seen.add(qid)
        item = {"id": qid, "section": str(q.get("section", "") or "General").strip()[:120], "text": text,
                "type": qtype, "weight": 0}
        if qtype == "yes_no":
            weight = int(q.get("weight") or 0)
            item["weight"] = max(0, min(3, weight))
            good = str(q.get("good", "yes") or "yes").strip().lower()
            item["good"] = "no" if good in ("no", "n", "false") else "yes"
            if q.get("evidence") in (True, "true", "yes", "y", "1", 1):
                item["evidence"] = True
        if qtype == "choice":
            opts = q.get("options") or []
            if isinstance(opts, str):
                opts = [o for o in re.split(r"[|;\n]", opts)]
            item["options"] = [str(o).strip()[:200] for o in opts if str(o).strip()][:20]
        guidance = str(q.get("guidance", "") or "").strip()[:1000]
        if guidance:
            item["guidance"] = guidance
        refs = str(q.get("refs", "") or "").strip()[:200]
        if refs:
            item["refs"] = refs
        out.append(item)
    if not out:
        raise ContentError("Add at least one question")
    validate_questions(out, "questionnaire")
    return out


# ---------------------------------------------------------------- import / export

COLUMNS = ["Section", "Question", "Type", "Weight", "Expected answer", "Evidence required", "Options", "Guidance",
           "Reference", "ID"]
_HEADER_KEYS = {"section": "section", "domain": "section", "category": "section", "question": "text", "text": "text",
                "type": "type", "answer type": "type", "weight": "weight", "score": "weight",
                "expected answer": "good", "good answer": "good", "expected": "good", "evidence required": "evidence",
                "evidence": "evidence", "options": "options", "choices": "options", "guidance": "guidance",
                "help": "guidance", "reference": "refs", "refs": "refs", "mapping": "refs", "id": "id"}


def parse_upload(filename: str, data: bytes) -> list[dict]:
    """Read questions from .xlsx or .csv. The first row is the header; only 'Question' is required."""
    if len(data) > IMPORT_MAX_BYTES:
        raise ContentError("Files up to 5 MB can be imported")
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as e:  # corrupt or not really xlsx
            raise ContentError("This isn't a readable .xlsx file") from e
        rows = [[("" if c is None else str(c)) for c in r] for r in wb.active.iter_rows(values_only=True,
                                                                                       max_row=MAX_QUESTIONS + 1)]
    elif name.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))[: MAX_QUESTIONS + 1]
    else:
        raise ContentError("Upload an Excel (.xlsx) or CSV file")
    if not rows:
        raise ContentError("The file is empty")
    header = [_HEADER_KEYS.get(h.strip().lower(), "") for h in rows[0]]
    if "text" not in header:
        raise ContentError("The first row must be a header with a 'Question' column")
    out = []
    for r in rows[1:]:
        item = {header[i]: (r[i] if i < len(r) else "") for i in range(len(header)) if header[i]}
        if not str(item.get("text", "")).strip():
            continue
        if not item.get("type"):
            item["type"] = "choice" if item.get("options") else "yes_no"
        if item.get("weight") in ("", None):
            item["weight"] = 1 if TYPE_ALIASES.get(str(item["type"]).lower()) == "yes_no" else 0
        try:
            item["weight"] = int(float(item["weight"]))
        except (TypeError, ValueError):
            item["weight"] = 0
        out.append(item)
    return clean_questions(out)


def _safe_cell(v) -> str:
    """Stop spreadsheet formula injection from vendor-supplied text."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def export_xlsx(title: str, questions: list[dict], answers: dict | None = None, meta: list[tuple] = ()) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Questionnaire"
    head = COLUMNS + (["Answer", "Comment"] if answers is not None else [])
    ws.append([_safe_cell(title)])
    ws["A1"].font = Font(bold=True, size=14)
    for k, v in meta:
        ws.append([_safe_cell(k), _safe_cell(v)])
    ws.append([])
    ws.append(head)
    hdr_row = ws.max_row
    for c in ws[hdr_row]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F2A5C")
    labels = {"yes_no": "Yes/No", "text": "Text", "choice": "Choice"}
    for q in questions:
        row = [q.get("section", ""), q["text"], labels.get(q["type"], q["type"]), q.get("weight", 0),
               q.get("good", "") if q["type"] == "yes_no" else "", "Yes" if q.get("evidence") else "",
               " | ".join(q.get("options", [])), q.get("guidance", ""), q.get("refs", ""), q["id"]]
        if answers is not None:
            a = answers.get(q["id"]) or {}
            row += [{"yes": "Yes", "no": "No", "na": "N/A"}.get(a.get("answer", ""), a.get("answer", "")),
                    a.get("comment", "")]
        ws.append([_safe_cell(v) for v in row])
    widths = [26, 70, 10, 8, 10, 10, 30, 40, 22, 10, 14, 40]
    for i, w in enumerate(widths[: len(head)]):
        ws.column_dimensions[chr(65 + i)].width = w
    for r in ws.iter_rows(min_row=hdr_row + 1):
        for c in r:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = ws.cell(row=hdr_row + 1, column=1)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- links and reminders


def issue_link(a: VendorAssessment, extend_days: int | None = None) -> str:
    """Give the assessment a fresh link (old links stop working). Used for sending and reminders."""
    token, token_hash = new_token()
    a.token_hash = token_hash
    now = datetime.now(timezone.utc)
    if extend_days and a.expires_at <= now + timedelta(days=3):
        a.expires_at = now + timedelta(days=extend_days)  # expired or about to: give them time to answer
    return f"{get_settings().public_url.rstrip('/')}/q/{token}"


def invitation_text(org_name: str, vendor_name: str, items: list[tuple[str, int, str]], expires: datetime,
                    reminder: bool = False) -> str:
    lines = [f"- {title} ({n} questions): {link}" for title, n, link in items]
    opener = (f"This is a reminder that {org_name} is waiting for {vendor_name}'s answers to:" if reminder else
              f"{org_name} has asked {vendor_name} to complete the following security "
              f"questionnaire{'s' if len(items) > 1 else ''}:")
    return (f"Hello,\n\n{opener}\n\n" + "\n".join(lines) +
            "\n\nYou can save and come back before submitting, upload certificates (ISO 27001, SOC 2) and add "
            "comments to any answer. Where a question doesn't apply, choose N/A and say why.\n\n"
            f"The link{'s expire' if len(items) > 1 else ' expires'} on {expires:%d %b %Y}. "
            "Please don't forward it outside your organisation.")


def status_of(a: VendorAssessment, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if a.cancelled_at:
        return "cancelled"
    if a.status in ("sent", "in_progress") and a.expires_at <= now:
        return "expired"
    return a.status


def send_reminders(db: Session, org: Organization, now: datetime) -> int:
    """Once per questionnaire, three days before expiry, send a fresh link to vendors who haven't submitted."""
    due = db.scalars(select(VendorAssessment).where(
        VendorAssessment.org_id == org.id, VendorAssessment.status.in_(("sent", "in_progress")),
        VendorAssessment.cancelled_at.is_(None), VendorAssessment.reminders_sent == 0,
        VendorAssessment.expires_at > now, VendorAssessment.expires_at <= now + timedelta(days=3))).all()
    for a in due:
        v = db.get(Vendor, a.vendor_id)
        link = issue_link(a)
        a.reminders_sent += 1
        a.last_reminded_at = now
        db.flush()
        notify.send_email_safely([a.sent_to_email], f"Reminder: {org.name} security questionnaire",
                                 invitation_text(org.name, v.name, [(a.template_title or a.template_slug,
                                                                     len(a.questions or []), link)],
                                                 a.expires_at, reminder=True))
    return len(due)
