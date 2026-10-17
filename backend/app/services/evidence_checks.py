"""Automatic checks on uploaded evidence. They don't decide whether evidence is good (people do); they catch the common
problems early: the same file reused from an earlier period, documents dated before the review period, blank
templates, broken links and files that changed after upload.

Each check is {"code", "severity": "info" | "warn", "message"}. Warnings are shown to the reviewer and the auditor.
"""
import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import httpx
from defusedxml import ElementTree as ET
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, Evidence
from app.net_guard import UnsafeTargetError, check_host

log = logging.getLogger("evidence_checks")

MAX_TEXT = 60_000
MAX_PDF_PAGES = 30
# How far back evidence may be dated and still belong to the current review period.
PERIOD_DAYS = {"continuous": 92, "monthly": 31, "quarterly": 92, "semiannual": 183, "annual": 366}
PLACEHOLDERS = re.compile(
    r"\[(?:company|organi[sz]ation|insert|name|date|todo|tbd|x+)[^\]]{0,40}\]|<insert[^>]{0,40}>|\{\{[^}]{1,40}\}\}"
    r"|lorem ipsum|\bxx/xx/xxxx\b|\bTBD\b|\[TODO", re.I)
LINK_RECHECK_DAYS = 7
_transport: httpx.BaseTransport | None = None  # tests inject a MockTransport


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_digest(value: str) -> bool:
    return bool(value) and len(value) == 64


def period_start(frequency: str, today: date | None = None) -> date | None:
    days = PERIOD_DAYS.get(frequency)
    return (today or date.today()) - timedelta(days=days) if days else None


# ---------------------------------------------------------------- reading files


@dataclass
class Extracted:
    text: str = ""
    document_date: date | None = None
    kind: str = "other"  # text | pdf | office | image | archive | other
    readable: bool = True  # False for scanned PDFs and legacy Office files
    notes: list[str] = field(default_factory=list)


def _date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", str(value))
    if not m:
        return None
    try:
        d = date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    return d if date(1995, 1, 1) <= d <= date.today() + timedelta(days=3650) else None


def _office_dates(z: zipfile.ZipFile) -> date | None:
    try:
        info = z.getinfo("docProps/core.xml")
    except KeyError:
        return None
    if info.file_size > 200_000:
        return None
    root = ET.fromstring(z.read(info), forbid_dtd=True)
    found = {el.tag.rsplit("}", 1)[-1]: el.text for el in root}
    return _date(found.get("modified")) or _date(found.get("created"))


def _xml_text(z: zipfile.ZipFile, names: list[str], limit: int) -> str:
    out: list[str] = []
    for n in names:
        info = z.getinfo(n)
        if info.file_size > 20_000_000:
            continue
        root = ET.fromstring(z.read(info), forbid_dtd=True)
        out.append(" ".join(t.text for t in root.iter() if t.text and t.tag.endswith(("}t", "}v"))))
        if sum(len(x) for x in out) > limit:
            break
    return "\n".join(out)[:limit]


def extract(file_name: str, data: bytes) -> Extracted:
    """Best-effort text and document date. Never raises: unreadable files just come back without text."""
    ext = ("." + file_name.rsplit(".", 1)[-1].lower()) if "." in file_name else ""
    try:
        if ext in (".txt", ".csv", ".json", ".md", ".log", ".yaml", ".yml"):
            return Extracted(text=data[:MAX_TEXT * 2].decode("utf-8", "replace")[:MAX_TEXT], kind="text")
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                return Extracted(kind="pdf", readable=False, notes=["The PDF is password protected"])
            meta = reader.metadata or {}
            doc_date = _date(getattr(meta, "modification_date", None)) or _date(getattr(meta, "creation_date", None))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:MAX_PDF_PAGES])[:MAX_TEXT]
            return Extracted(text=text, document_date=doc_date, kind="pdf", readable=bool(text.strip()))
        if ext in (".docx", ".xlsx", ".pptx"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if ext == ".docx":
                    parts = [n for n in names if n == "word/document.xml"]
                elif ext == ".pptx":
                    parts = sorted(n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
                else:
                    parts = [n for n in names if n == "xl/sharedStrings.xml"]
                return Extracted(text=_xml_text(z, parts, MAX_TEXT), document_date=_office_dates(z), kind="office")
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            return Extracted(kind="image", readable=False)
        if ext == ".zip":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return Extracted(text="\n".join(z.namelist()[:500]), kind="archive")
        if ext in (".doc", ".xls", ".ppt"):
            return Extracted(kind="office", readable=False, notes=["Older Office format; text can't be read"])
    except Exception as e:  # noqa: BLE001 - corrupt or unusual files simply aren't analysed
        log.info("could not read %s: %s", file_name, e)
        return Extracted(kind="other", readable=False, notes=["The file couldn't be read for automatic checks"])
    return Extracted(readable=False)


# ---------------------------------------------------------------- checks


def _check(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def run_checks(db: Session, ev: Evidence, control: Control, extracted: Extracted | None,
               today: date | None = None) -> list[dict]:
    today = today or date.today()
    out: list[dict] = []
    start = period_start(control.frequency, today)

    if is_digest(ev.sha256):
        same = db.execute(select(Evidence.id, Evidence.control_id, Evidence.collected_at, Control.code)
                          .join(Control, Control.id == Evidence.control_id)
                          .where(Evidence.org_id == ev.org_id, Evidence.sha256 == ev.sha256, Evidence.id != ev.id)
                          ).all()
        earlier_here = [r for r in same if r.control_id == control.id]
        if earlier_here:
            first = min(r.collected_at for r in earlier_here).date()
            if start and first < start:
                out.append(_check("reused_file", "warn",
                                  f"This exact file was already uploaded on {first:%d %b %Y}, before this review "
                                  f"period. Evidence should show the control working in the current period."))
            else:
                out.append(_check("duplicate_upload", "info", f"The same file was already added to this control on "
                                                               f"{first:%d %b %Y}."))
        others = sorted({r.code for r in same if r.control_id != control.id})
        if others:
            out.append(_check("shared_file", "info", "The same file is also evidence for "
                                                     + ", ".join(others[:6]) + (" and more" if len(others) > 6 else "")
                              + ". That's fine for a policy covering several controls; otherwise check it fits."))

    if extracted:
        d = extracted.document_date
        if d and start and d < start:
            out.append(_check("stale_document", "warn",
                              f"The document is dated {d:%d %b %Y}, before this review period (from {start:%d %b %Y})."
                              " Check it is the current version, or that it was reviewed recently."))
        if d and d > today + timedelta(days=1):
            out.append(_check("future_date", "warn", f"The document is dated in the future ({d:%d %b %Y})."))
        text = extracted.text or ""
        hits = sorted({m.group(0).strip()[:40] for m in PLACEHOLDERS.finditer(text)})
        if hits:
            out.append(_check("blank_template", "warn", "Placeholders found, so this may be an unfinished template: "
                              + ", ".join(f"“{h}”" for h in hits[:4])))
        words = len(re.findall(r"\w{2,}", text))
        if extracted.kind in ("pdf", "office") and extracted.readable and words < 25:
            out.append(_check("little_text", "warn", f"Only {words} words found. Is this the completed document?"))
        if extracted.kind == "pdf" and not extracted.readable and not extracted.notes:
            out.append(_check("no_text", "info", "No readable text (a scan or image-only PDF). The reviewer should "
                                                  "open it and check it."))
        for n in extracted.notes:
            out.append(_check("unreadable", "info", n + "; the reviewer should open it and check it."))
        if extracted.kind == "image":
            out.append(_check("screenshot", "info", "Screenshots should show the date and the system or account they "
                                                     "come from."))

    if ev.kind == "note":
        out.append(_check("note_only", "info", "A note is a statement, not proof. Attach the record, export or "
                                               "screenshot if one exists."))
    if ev.kind == "link" and ev.url.startswith("http://"):
        out.append(_check("insecure_link", "info", "The link isn't HTTPS."))
    return out


def evaluate(db: Session, ev: Evidence, control: Control, data: bytes | None) -> None:
    """Fingerprint, read and check new evidence (called when it's added)."""
    extracted = None
    if data is not None:
        ev.sha256 = sha256(data)
        extracted = extract(ev.file_name, data)
        ev.document_date = extracted.document_date
    ev.checks = run_checks(db, ev, control, extracted)


# ---------------------------------------------------------------- links


def check_link(url: str) -> dict | None:
    """Fetch a link (following up to 3 redirects, each checked for SSRF) and return a check, or None if fine."""
    current = url
    try:
        with httpx.Client(timeout=8, follow_redirects=False, transport=_transport,
                          headers={"User-Agent": "Anupalan evidence link check"}) as client:
            for _ in range(4):
                parsed = urlparse(current)
                if parsed.scheme not in ("http", "https") or not parsed.hostname:
                    return _check("link_broken", "warn", "The link isn't a web address.")
                try:
                    check_host(parsed.hostname)
                except UnsafeTargetError:
                    return _check("link_internal", "info", "The link points to an internal address that can't be "
                                                           "checked from here. Make sure the auditor can open it.")
                r = client.get(current)
                if r.is_redirect and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    continue
                break
    except httpx.HTTPError:
        return _check("link_broken", "warn", "The link couldn't be reached.")
    if r.status_code in (401, 403) or "login" in str(r.url).lower() or "signin" in str(r.url).lower():
        return _check("link_signin", "info", "The link needs a sign-in. Make sure the auditor will have access, or "
                                             "attach an export instead.")
    if r.status_code in (404, 410):
        return _check("link_broken", "warn", f"The link returns “not found” ({r.status_code}).")
    if r.status_code >= 400:
        return _check("link_broken", "warn", f"The link returned an error ({r.status_code}).")
    return None


def recheck_links(db: Session, org_id, limit: int = 50) -> int:
    """Worker: check links that haven't been checked in a week."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LINK_RECHECK_DAYS)).isoformat()
    rows = db.scalars(select(Evidence).where(Evidence.org_id == org_id, Evidence.kind == "link")).all()
    done = 0
    for ev in rows:
        last = (ev.data or {}).get("link_checked_at", "")
        if last and last > cutoff:
            continue
        result = check_link(ev.url)
        keep = [c for c in (ev.checks or []) if not c["code"].startswith("link_")]
        ev.checks = keep + ([result] if result else [])
        ev.data = {**(ev.data or {}), "link_checked_at": datetime.now(timezone.utc).isoformat()}
        done += 1
        if done >= limit:
            break
    return done


def backfill_hashes(db: Session, org_id, limit: int = 200) -> int:
    """Worker: fingerprint file evidence uploaded before fingerprints existed."""
    from app.services import storage

    rows = db.scalars(select(Evidence).where(Evidence.org_id == org_id, Evidence.file_key != "",
                                             Evidence.sha256 == "").limit(limit)).all()
    for ev in rows:
        try:
            ev.sha256 = sha256(storage.read(org_id, ev.file_key))
            ev.data = {**(ev.data or {}), "fingerprinted_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:  # noqa: BLE001 - a missing file shouldn't stop the batch
            log.warning("could not fingerprint evidence %s: %s", ev.id, e)
            ev.sha256 = "missing"  # not a real digest (see is_digest); stops retrying every run
    return len(rows)
