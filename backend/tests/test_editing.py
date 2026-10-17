"""Editing controls, (bulk) owner assignment, policy editing and importing Word/PDF documents."""
import io
import zipfile
from xml.sax.saxutils import escape

from sqlalchemy import text

from tests.conftest import make_client

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def _join(owner, email, role, name):
    body = {"email": email, "role": role, **({"access_days": 14} if role == "auditor" else {})}
    inv = owner.post("/api/org/invitations", json=body).json()
    c = make_client()
    r = c.post("/api/auth/invitations/accept", json={"token": inv["invite_url"].rsplit("/", 1)[1],
                                                     "full_name": name, "password": "Saffron-Bicycle-Ladder-31"})
    assert r.status_code in (200, 201), r.text
    members = owner.get("/api/org/members").json()
    uid = next(m["user"]["id"] for m in members if m["user"]["email"] == email)
    return c, uid


def _docx(body_xml: str, numbering: str | None = None, rels: str | None = None, styles: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document {W_NS}><w:body>{body_xml}</w:body></w:document>")
        if numbering:
            z.writestr("word/numbering.xml", f"<w:numbering {W_NS}>{numbering}</w:numbering>")
        if rels:
            z.writestr("word/_rels/document.xml.rels",
                       f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       f"{rels}</Relationships>")
        if styles:
            z.writestr("word/styles.xml", f"<w:styles {W_NS}>{styles}</w:styles>")
    return buf.getvalue()


def _p(text_, style=None, num=None, bold=False):
    ppr = ""
    if style or num:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + (
            f'<w:numPr><w:ilvl w:val="{num[1]}"/><w:numId w:val="{num[0]}"/></w:numPr>' if num else "") + "</w:pPr>"
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f"<w:p>{ppr}<w:r>{rpr}<w:t>{escape(text_)}</w:t></w:r></w:p>"


# ================================================================ controls


def test_edit_control_details_and_reassign_owner(owner, db):
    c = owner.get("/api/controls").json()[0]
    member, mid = _join(owner, "m@acme.in", "member", "Mira Shah")
    r = owner.patch(f"/api/controls/{c['id']}", json={"title": "  Access is reviewed  ", "category": "Access",
                                                      "frequency": "quarterly", "description": "Our way",
                                                      "owner_id": mid})
    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["title"], out["category"], out["frequency"], out["owner"]["id"]) == (
        "Access is reviewed", "Access", "quarterly", mid)
    # the new owner hears about it
    n = db.execute(text("SELECT title, recipients FROM notifications WHERE event = 'control_assigned'")).all()
    assert len(n) == 1 and n[0].recipients == ["m@acme.in"] and c["code"] in n[0].title
    # empty titles are rejected; clearing the owner works
    assert owner.patch(f"/api/controls/{c['id']}", json={"title": "   "}).status_code in (400, 422)
    assert owner.patch(f"/api/controls/{c['id']}", json={"clear_owner": True}).json()["owner"] is None
    log = db.execute(text("SELECT detail FROM audit_logs WHERE action = 'control.updated' ORDER BY seq")).scalars().all()
    assert "title" in log[0]["fields"] and log[0]["owner_id"] == mid


def test_auditors_cannot_own_and_cannot_edit(owner):
    c = owner.get("/api/controls").json()[0]
    aud, aid = _join(owner, "aud@firm.in", "auditor", "Ext Auditor")
    assert owner.patch(f"/api/controls/{c['id']}", json={"owner_id": aid}).status_code == 400
    assert aud.patch(f"/api/controls/{c['id']}", json={"title": "x"}).status_code == 403
    assert aud.post("/api/controls/bulk", json={"ids": [c["id"]], "status": "implemented"}).status_code == 403


def test_bulk_assign_controls(owner, db):
    controls = owner.get("/api/controls").json()[:5]
    _, mid = _join(owner, "m@acme.in", "member", "Mira Shah")
    ids = [c["id"] for c in controls]
    r = owner.post("/api/controls/bulk", json={"ids": ids, "owner_id": mid, "status": "in_progress"})
    assert r.status_code == 200 and r.json() == {"updated": 5}
    after = {c["id"]: c for c in owner.get("/api/controls").json()}
    assert all(after[i]["owner"]["id"] == mid and after[i]["status"] == "in_progress" for i in ids)
    n = db.execute(text("SELECT title FROM notifications WHERE event = 'control_assigned'")).scalars().all()
    assert n == ["Asha Rao assigned you 5 controls"]
    # N/A needs a justification per control, so bulk can't set it; empty requests and foreign ids are refused
    assert owner.post("/api/controls/bulk", json={"ids": ids, "status": "not_applicable"}).status_code == 422
    assert owner.post("/api/controls/bulk", json={"ids": ids}).status_code == 400
    other = make_client()
    from tests.conftest import onboard, signup, verify_email
    signup(other, email="o@beta.in", org="Beta")
    verify_email("o@beta.in")
    onboard(other)
    foreign = other.get("/api/controls").json()[0]["id"]
    assert owner.post("/api/controls/bulk", json={"ids": [foreign], "clear_owner": True}).status_code == 404
    assert owner.post("/api/controls/bulk", json={"ids": ids, "clear_owner": True}).status_code == 200
    assert all(c["owner"] is None for c in owner.get("/api/controls").json() if c["id"] in ids)


# ================================================================ policies


def test_create_and_edit_policy_with_owner_and_controls(owner):
    _, mid = _join(owner, "m@acme.in", "member", "Mira Shah")
    code = owner.get("/api/controls").json()[0]["code"]
    r = owner.post("/api/policies", json={"title": "Remote work", "body_md": "# Remote work\n\nUse the VPN.",
                                          "control_codes": [code.lower()], "owner_id": mid})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["control_codes"] == [code] and p["owner"]["id"] == mid
    assert owner.patch(f"/api/policies/{p['id']}", json={"control_codes": ["NOPE-99"]}).status_code == 400
    r = owner.patch(f"/api/policies/{p['id']}", json={"body_md": "Updated", "clear_owner": True})
    assert r.json()["body_md"] == "Updated" and r.json()["owner"] is None
    assert owner.patch(f"/api/policies/{p['id']}", json={"body_md": "x" * 400_001}).status_code == 422


def test_import_docx_to_safe_html(owner):
    numbering = ('<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl>'
                 '</w:abstractNum><w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/>'
                 '</w:lvl></w:abstractNum><w:num w:numId="5"><w:abstractNumId w:val="1"/></w:num>'
                 '<w:num w:numId="6"><w:abstractNumId w:val="2"/></w:num>')
    styles = '<w:style w:styleId="Kop1"><w:name w:val="heading 1"/></w:style>'
    rels = ('<Relationship Id="rId9" Target="https://example.com/x" TargetMode="External"/>'
            '<Relationship Id="rId10" Target="javascript:alert(1)" TargetMode="External"/>')
    body = (_p("Access Policy", style="Kop1") + _p("Purpose", style="Heading2") + _p("<script>x</script> & more")
            + _p("Bold", bold=True) + _p("one", num=("5", 0)) + _p("two", num=("5", 0)) + _p("step", num=("6", 0))
            + '<w:p><w:hyperlink r:id="rId9"><w:r><w:t>site</w:t></w:r></w:hyperlink>'
            '<w:hyperlink r:id="rId10"><w:r><w:t>bad</w:t></w:r></w:hyperlink></w:p>'
            '<w:tbl><w:tr><w:tc>' + _p("Role") + '</w:tc><w:tc>' + _p("Duty") + '</w:tc></w:tr>'
            '<w:tr><w:tc>' + _p("CISO") + '</w:tc><w:tc>' + _p("Own it") + '</w:tc></w:tr></w:tbl>')
    f = {"file": ("Access_Policy.docx", _docx(body, numbering, rels, styles),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    r = owner.post("/api/policies/import", files=f)
    assert r.status_code == 200, r.text
    h = r.json()["html"]
    assert r.json()["title"] == "Access Policy"
    assert "<h1>Access Policy</h1>" in h and "<h2>Purpose</h2>" in h
    assert "&lt;script&gt;x&lt;/script&gt; &amp; more" in h and "<script" not in h
    assert "<strong>Bold</strong>" in h
    assert "<ul><li>one</li><li>two</li></ul><ol><li>step</li></ol>" in h
    assert '<a href="https://example.com/x">site</a>' in h and "javascript" not in h and "bad" in h
    assert "<th><p>Role</p></th>" in h and "<td><p>Own it</p></td>" in h


def test_import_rejects_hostile_and_unsupported_files(owner):
    bomb = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            '<w:p><w:r><w:t>&lol2;</w:t></w:r></w:p></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", bomb)
    r = owner.post("/api/policies/import", files={"file": ("x.docx", buf.getvalue())})
    assert r.status_code == 422 and "valid Word" in r.json()["detail"]
    assert owner.post("/api/policies/import", files={"file": ("x.doc", b"\xd0\xcf\x11\xe0")}).status_code == 422
    assert owner.post("/api/policies/import", files={"file": ("x.pdf", b"%PDF-1.4 garbage")}).status_code == 422
    assert owner.post("/api/policies/import", files={"file": ("x.docx", b"")}).status_code == 400
    big = b"PK" + b"0" * (10 * 1024 * 1024)
    assert owner.post("/api/policies/import", files={"file": ("x.docx", big)}).status_code == 413


def test_import_pdf_text(owner):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    w = PdfWriter()
    page = w.add_blank_page(612, 792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject(
        {NameObject("/F1"): w._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 700 Td (Backup policy) Tj ET")
    page[NameObject("/Contents")] = w._add_object(stream)
    buf = io.BytesIO()
    w.write(buf)
    r = owner.post("/api/policies/import", files={"file": ("backup.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 200, r.text
    assert "<p>Backup policy</p>" in r.json()["html"] and r.json()["warnings"]
