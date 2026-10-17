"""Turn an uploaded policy document (.docx or .pdf) into safe HTML for the policy editor.

Nothing is stored: the editor shows the result for review and the user saves it like any other edit. All text is
HTML-escaped here and the only tags emitted are a fixed set (h1-h3, p, ul/ol/li, strong, em, a, table), so the output
can't carry scripts or styles from the source file. DOCX parsing uses defusedxml with size limits against zip bombs.
"""
import html
import io
import re
import zipfile

from defusedxml import ElementTree as ET

MAX_PART_BYTES = 30 * 1024 * 1024  # largest single XML part we'll inflate
MAX_PDF_PAGES = 300
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class ImportError_(ValueError):
    """The file can't be converted; the message is shown to the user."""


def convert(filename: str, data: bytes) -> dict:
    name = (filename or "").lower()
    if name.endswith(".docx") or data[:2] == b"PK" and not name.endswith(".pdf"):
        return {"html": docx_to_html(data), "warnings": []}
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        return {"html": pdf_to_html(data),
                "warnings": ["PDFs don't keep headings or lists. Check the formatting before saving."]}
    if name.endswith(".doc"):
        raise ImportError_("Old .doc files aren't supported. Open it in Word or Google Docs and save as .docx.")
    raise ImportError_("Upload a .docx or .pdf file. For .md, .txt or .html files, the editor reads them directly.")


# ---------------------------------------------------------------- docx


def _read_part(z: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART_BYTES:
        raise ImportError_("This document is too large to import.")
    with z.open(info) as f:
        out = f.read(MAX_PART_BYTES + 1)
    if len(out) > MAX_PART_BYTES:
        raise ImportError_("This document is too large to import.")
    return out


def _parse(raw: bytes):
    try:
        return ET.fromstring(raw, forbid_dtd=True)
    except Exception as e:  # defusedxml raises several types for hostile or broken XML
        raise ImportError_("This file isn't a valid Word document.") from e


def docx_to_html(data: bytes) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ImportError_("This file isn't a valid Word document.") from e
    with z:
        doc_raw = _read_part(z, "word/document.xml")
        if doc_raw is None:
            raise ImportError_("This file isn't a valid Word document.")
        doc = _parse(doc_raw)
        styles = _styles(z)
        numbering = _numbering(z)
        links = _links(z)
    body = doc.find(f"{W}body")
    if body is None:
        return ""
    out: list[str] = []
    list_stack: list[tuple[str, str]] = []  # open lists, one per level: (tag, list id)

    def close_lists(to: int = 0):
        while len(list_stack) > to:
            out.append(f"</li></{list_stack.pop()[0]}>")

    for el in body:
        if el.tag == f"{W}p":
            kind, level, ordered, list_id = _para_kind(el, styles, numbering)
            text = _runs(el, links)
            if kind == "li":
                tag = "ol" if ordered else "ul"
                if len(list_stack) > level + 1:
                    close_lists(level + 1)
                if len(list_stack) == level + 1 and list_stack[-1] != (tag, list_id):
                    close_lists(level)  # a different list starts at this level
                if len(list_stack) == level + 1:
                    out.append("</li><li>")
                else:
                    while len(list_stack) < level + 1:
                        list_stack.append((tag, list_id))
                        out.append(f"<{tag}><li>")
                out.append(text)
                continue
            close_lists()
            if not text.strip():
                continue
            out.append(f"<{kind}>{text}</{kind}>")
        elif el.tag == f"{W}tbl":
            close_lists()
            out.append(_table(el, links))
    close_lists()
    return "".join(out)


def _styles(z) -> dict[str, str]:
    raw = _read_part(z, "word/styles.xml")
    if raw is None:
        return {}
    out = {}
    for s in _parse(raw).iter(f"{W}style"):
        name = s.find(f"{W}name")
        if name is not None:
            out[s.get(f"{W}styleId", "")] = (name.get(f"{W}val") or "").lower()
    return out


def _numbering(z) -> dict[tuple[str, int], bool]:
    """(numId, level) -> ordered?"""
    raw = _read_part(z, "word/numbering.xml")
    if raw is None:
        return {}
    root = _parse(raw)
    abstract = {}
    for a in root.iter(f"{W}abstractNum"):
        levels = {}
        for lvl in a.iter(f"{W}lvl"):
            fmt = lvl.find(f"{W}numFmt")
            levels[int(lvl.get(f"{W}ilvl", "0"))] = fmt is not None and fmt.get(f"{W}val") not in ("bullet", "none")
        abstract[a.get(f"{W}abstractNumId")] = levels
    out = {}
    for n in root.iter(f"{W}num"):
        ref = n.find(f"{W}abstractNumId")
        if ref is not None:
            for lvl, ordered in abstract.get(ref.get(f"{W}val"), {}).items():
                out[(n.get(f"{W}numId"), lvl)] = ordered
    return out


def _links(z) -> dict[str, str]:
    raw = _read_part(z, "word/_rels/document.xml.rels")
    if raw is None:
        return {}
    return {r.get("Id"): r.get("Target", "") for r in _parse(raw).iter(f"{REL}Relationship")
            if r.get("TargetMode") == "External"}


def _para_kind(p, styles, numbering) -> tuple[str, int, bool, str]:
    ppr = p.find(f"{W}pPr")
    style = ""
    if ppr is not None:
        ps = ppr.find(f"{W}pStyle")
        if ps is not None:
            sid = ps.get(f"{W}val", "")
            style = styles.get(sid, sid.lower())
        num = ppr.find(f"{W}numPr")
        if num is not None:
            ilvl = num.find(f"{W}ilvl")
            nid = num.find(f"{W}numId")
            level = min(int(ilvl.get(f"{W}val", "0")) if ilvl is not None else 0, 5)
            num_id = nid.get(f"{W}val") if nid is not None else None
            if num_id and num_id != "0":
                return "li", level, numbering.get((num_id, level), False), num_id
    if style in ("title",) or re.fullmatch(r"heading ?1", style):
        return "h1", 0, False, ""
    if re.fullmatch(r"heading ?2", style) or style == "subtitle":
        return "h2", 0, False, ""
    if re.fullmatch(r"heading ?[3-9]", style):
        return "h3", 0, False, ""
    if "list" in style and "bullet" in style:
        return "li", 0, False, style
    if "list" in style and "number" in style:
        return "li", 0, True, style
    return "p", 0, False, ""


def _on(rpr, tag) -> bool:
    if rpr is None:
        return False
    el = rpr.find(f"{W}{tag}")
    return el is not None and el.get(f"{W}val", "true") not in ("0", "false", "none")


def _runs(p, links) -> str:
    parts: list[str] = []

    def run_text(r) -> str:
        bits = []
        for child in r:
            if child.tag == f"{W}t":
                bits.append(html.escape(child.text or ""))
            elif child.tag == f"{W}tab":
                bits.append(" ")
            elif child.tag in (f"{W}br", f"{W}cr"):
                bits.append("<br>")
        s = "".join(bits)
        if not s.strip():
            return s
        rpr = r.find(f"{W}rPr")
        if _on(rpr, "i"):
            s = f"<em>{s}</em>"
        if _on(rpr, "b"):
            s = f"<strong>{s}</strong>"
        return s

    for child in p:
        if child.tag == f"{W}r":
            parts.append(run_text(child))
        elif child.tag == f"{W}hyperlink":
            inner = "".join(run_text(r) for r in child.iter(f"{W}r"))
            href = links.get(child.get(f"{R}id"), "")
            if re.match(r"^(https?://|mailto:)", href, re.I):
                parts.append(f'<a href="{html.escape(href, quote=True)}">{inner}</a>')
            else:
                parts.append(inner)
        elif child.tag in (f"{W}ins", f"{W}smartTag", f"{W}sdt"):  # tracked insertions and wrappers keep their text
            parts.extend(run_text(r) for r in child.iter(f"{W}r"))
    return "".join(parts)


def _table(tbl, links) -> str:
    rows = []
    for i, tr in enumerate(tbl.iter(f"{W}tr")):
        cells = []
        for tc in tr.findall(f"{W}tc"):
            text = "<br>".join(t for t in (_runs(p, links) for p in tc.iter(f"{W}p")) if t.strip())
            tag = "th" if i == 0 else "td"
            cells.append(f"<{tag}><p>{text}</p></{tag}>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><tbody>{''.join(rows)}</tbody></table>" if rows else ""


# ---------------------------------------------------------------- pdf


def pdf_to_html(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ImportError_("This PDF is password protected. Remove the password and try again.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ImportError_(f"PDFs over {MAX_PDF_PAGES} pages can't be imported.")
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except ImportError_:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise ImportError_("This PDF couldn't be read.") from e
    if not text.strip():
        raise ImportError_("No text found. This may be a scanned PDF; paste the text instead.")
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        bullets = [ln for ln in lines if re.match(r"^[•\-•●▪*]\s+", ln)]
        if bullets and len(bullets) == len(lines):
            items = "".join(f"<li><p>{html.escape(_strip_bullet(ln))}</p></li>" for ln in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append(f"<p>{html.escape(' '.join(lines))}</p>")
    return "".join(out)


def _strip_bullet(line: str) -> str:
    return re.sub(r"^\S+\s+", "", line, count=1)
