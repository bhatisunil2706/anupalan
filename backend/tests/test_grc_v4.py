"""Risk register <-> Jira, new frameworks, the vendor questionnaire library, and the training programme
(department assignments, enrollments, certificates, company courses, phishing simulations)."""
import csv
import io
import json
from datetime import date, timedelta

import httpx
import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select, text

from app.integrations import REGISTRY
from app.models import (
    Integration,
    Organization,
    Person,
    PhishingTarget,
    Risk,
    TrainingAssignment,
    VendorAssessment,
)
from app.security import encrypt_json
from app.services import integrations as integ_service
from app.services import notify
from app.services.content import check_content
from tests.conftest import make_client, onboard, signup, verify_email


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body, **kw: sent.append(
        {"to": to, "subject": subject, "body": body, **kw}))
    return sent


def _join(owner, email, role="member", name="Mira Shah"):
    body = {"email": email, "role": role, **({"access_days": 14} if role == "auditor" else {})}
    inv = owner.post("/api/org/invitations", json=body).json()
    c = make_client()
    r = c.post("/api/auth/invitations/accept", json={"token": inv["invite_url"].rsplit("/", 1)[1],
                                                     "full_name": name, "password": "Saffron-Bicycle-Ladder-31"})
    assert r.status_code in (200, 201), r.text
    return c


# ================================================================ Jira risks


class FakeJira:
    def __init__(self):
        self.issues: dict[str, dict] = {}
        self.updates: list[tuple[str, dict]] = []
        self.extra: list[dict] = []  # issues created directly in Jira (for import)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/rest/api/3/issue":
            key = f"SEC-{len(self.issues) + 1}"
            self.issues[key] = {"fields": json.loads(request.content)["fields"], "status": ("To Do", "new")}
            return httpx.Response(201, json={"key": key})
        if request.method == "PUT" and path.startswith("/rest/api/3/issue/"):
            self.updates.append((path.rsplit("/", 1)[1], json.loads(request.content)["fields"]))
            return httpx.Response(204)
        if request.method == "POST" and path == "/rest/api/3/search/jql":
            jql = json.loads(request.content)["jql"]
            if jql.startswith("key in ("):
                keys = jql[len("key in ("):-1].split(",")
                return httpx.Response(200, json={"issues": [
                    {"key": k, "fields": {"status": {"name": self.issues[k]["status"][0],
                                                     "statusCategory": {"key": self.issues[k]["status"][1]}}}}
                    for k in keys if k in self.issues], "isLast": True})
            if jql == "bad jql":
                return httpx.Response(400, json={"errorMessages": ["Field 'bad' does not exist."]})
            return httpx.Response(200, json={"issues": self.extra, "isLast": True})
        return httpx.Response(404, json={})


@pytest.fixture
def jira(owner, db, monkeypatch):
    fake = FakeJira()
    org = db.scalar(select(Organization))
    db.add(Integration(org_id=org.id, provider="jira", status="connected",
                       config={"site": "https://acme.atlassian.net", "email": "a@acme.in", "project_key": "SEC",
                               "risk_import_jql": "project = SEC AND labels = risk"},
                       secret_encrypted=encrypt_json({"api_token": "t"})))
    db.commit()
    original = integ_service.jira_for_org

    def patched(db_, org_id, timeout=30):
        integ, conn = original(db_, org_id, timeout)
        if conn is None:
            return integ, conn
        return integ, REGISTRY["jira"](integ.config, {"api_token": "t"},
                                       client=httpx.Client(transport=httpx.MockTransport(fake.handler)))

    monkeypatch.setattr(integ_service, "jira_for_org", patched)
    return fake


def test_new_risk_creates_jira_issue_and_status_flows_back(owner, jira, db):
    status = owner.get("/api/risks/jira").json()
    assert status["connected"] and status["auto_create"] and status["project"] == "SEC"
    r = owner.post("/api/risks", json={"title": "Laptop theft exposes data", "likelihood": 4, "impact": 4,
                                       "treatment_plan": "Disk encryption on all laptops", "control_codes": ["AST-05"]})
    assert r.status_code == 201, r.text
    risk = r.json()
    assert risk["external_ref"] == "SEC-1" and risk["external_url"] == "https://acme.atlassian.net/browse/SEC-1"
    fields = jira.issues["SEC-1"]["fields"]
    assert fields["summary"] == "[Risk] Laptop theft exposes data" and "risk-high" in fields["labels"]
    assert "Risk score: 16" in json.dumps(fields["description"])

    # edits are pushed to the linked issue
    owner.put(f"/api/risks/{risk['id']}", json={**{k: risk[k] for k in ("title", "description", "category",
                                                                       "likelihood", "impact", "treatment",
                                                                       "treatment_plan", "status")},
                                                "likelihood": 2, "control_codes": ["AST-05"]})
    assert jira.updates and jira.updates[-1][0] == "SEC-1" and "risk-medium" in jira.updates[-1][1]["labels"]

    # done in Jira -> treated here; reopened -> open again
    jira.issues["SEC-1"]["status"] = ("Done", "done")
    out = owner.post("/api/risks/jira/sync").json()
    assert out["updated"] == 1
    got = {x["id"]: x for x in owner.get("/api/risks").json()}[risk["id"]]
    assert got["status"] == "treated" and got["external_status"] == "Done"
    jira.issues["SEC-1"]["status"] = ("In Progress", "indeterminate")
    owner.post("/api/risks/jira/sync")
    assert {x["id"]: x for x in owner.get("/api/risks").json()}[risk["id"]]["status"] == "open"
    log = db.execute(text("SELECT action FROM audit_logs WHERE action LIKE 'risk.jira%'")).scalars().all()
    assert "risk.jira_linked" in log and "risk.jira_synced" in log


def test_risks_imported_from_jira_jql_and_existing_risks_linked_on_demand(owner, jira, db):
    org = db.scalar(select(Organization))
    db.add(Risk(org_id=org.id, title="Added before Jira", likelihood=2, impact=2))
    db.commit()
    jira.extra = [{"key": "SEC-90", "fields": {
        "summary": "Third-party SDK collects device IDs", "status": {"name": "To Do", "statusCategory": {"key": "new"}},
        "description": {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "Found during a privacy review."}]}]},
        "assignee": {"emailAddress": "owner@acme.in"}}}]
    out = owner.post("/api/risks/jira/sync").json()
    assert out == {"pushed": 1, "updated": 0, "imported": 1}
    risks = {r["title"]: r for r in owner.get("/api/risks").json()}
    imported = risks["Third-party SDK collects device IDs"]
    assert imported["source"] == "jira" and imported["external_ref"] == "SEC-90"
    assert imported["description"] == "Found during a privacy review." and imported["owner"]["email"] == "owner@acme.in"
    assert risks["Added before Jira"]["external_ref"] == "SEC-1"
    # running again doesn't duplicate the import or re-push
    assert owner.post("/api/risks/jira/sync").json() == {"pushed": 0, "updated": 0, "imported": 0}
    # a risk can be linked on demand; a linked one can't be linked twice
    rid = owner.post("/api/risks", json={"title": "Another"}).json()["id"]
    assert owner.post(f"/api/risks/{rid}/jira").status_code == 409


def test_jira_down_does_not_block_saving_a_risk(owner, jira, monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(jira, "handler", boom)
    r = owner.post("/api/risks", json={"title": "Saved anyway"})
    assert r.status_code == 201 and r.json()["external_ref"] == ""
    assert "retried" in r.headers.get("X-Warning", "")


def test_risk_jira_requires_connection_and_writer(owner):
    assert owner.get("/api/risks/jira").json() == {"connected": False}
    assert owner.post("/api/risks/jira/sync").status_code == 400
    aud = _join(owner, "aud@firm.in", "auditor", "Ext Auditor")
    assert aud.post("/api/risks/jira/sync").status_code == 403


# ================================================================ frameworks


def test_all_frameworks_load_and_are_fully_mapped():
    counts = check_content()
    assert counts["frameworks"] == 18 and counts["requirements"] >= 750


def test_enable_new_frameworks_provisions_their_controls(owner):
    codes = {f["code"]: f for f in owner.get("/api/frameworks").json()}
    assert {"gdpr", "nist_csf", "hipaa", "pci_dss", "iso42001", "rbi_cyber", "sebi_cscrf"} <= set(codes)
    assert "rbi_itgrc" not in codes  # replaced by the 2026 Directions
    assert codes["nist_csf"]["requirement_count"] == 106 and codes["dpdp"]["group"] == "India"
    before = {c["code"] for c in owner.get("/api/controls").json()}
    r = owner.post("/api/frameworks/iso42001/enable").json()
    assert r["controls_created"] >= 6
    after = {c["code"] for c in owner.get("/api/controls").json()}
    assert {"AI-01", "AI-02", "AI-03", "AI-04", "AI-05", "AI-06"} <= after - before
    owner.post("/api/frameworks/pci_dss/enable")
    after = {c["code"] for c in owner.get("/api/controls").json()}
    assert {"PCI-01", "PCI-02", "PCI-03", "PCI-04"} <= after and "PCI-05" not in after  # card-present is opt-in
    owner.patch("/api/org", json={"profile": {"pci_card_present": True}})
    owner.post("/api/frameworks/pci_dss/enable")
    assert "PCI-05" in {c["code"] for c in owner.get("/api/controls").json()}
    flags = {f["key"]: f["framework"] for f in owner.get("/api/org/profile-flags").json()}
    assert flags["soc2_privacy"] == "soc2" and flags["eu_representative_required"] == "gdpr"


# ================================================================ vendor questionnaires


def _vendor(owner, tier="high"):
    return owner.post("/api/vendors", json={"name": "CloudCo", "tier": tier, "is_processor": True}).json()["id"]


def _token(link: str) -> str:
    return link.rsplit("/", 1)[1]


def test_library_lists_standard_sets_with_recommendations(owner):
    lib = {t["slug"]: t for t in owner.get("/api/questionnaires").json()}
    assert lib["standard-full"]["questions"] >= 90 and lib["standard-full"]["recommended_for"] == ["high", "critical"]
    assert lib["standard-lite"]["kind"] == "core" and lib["ai-vendor"]["kind"] == "addon"
    full = owner.get("/api/questionnaires/standard-full").json()
    assert any(q["type"] == "choice" for q in full["questions_list"])
    x = owner.get("/api/questionnaires/standard-full/export")
    assert x.status_code == 200
    ws = load_workbook(io.BytesIO(x.content)).active
    assert any(row and row[1] and "multi-factor" in str(row[1]).lower() for row in ws.iter_rows(values_only=True))


def test_send_core_plus_addons_snapshots_questions_and_lists_them(owner, mail, db):
    vid = _vendor(owner)
    r = owner.post(f"/api/vendors/{vid}/assessments",
                   json={"template_slugs": ["standard-lite", "dpdp-processor"], "email": "sec@cloudco.com"})
    assert r.status_code == 201, r.text
    sent = r.json()["sent"]
    assert [s["template_title"] for s in sent] == ["Standard security questionnaire (Lite)",
                                                   "Add-on: DPDP Data Processor"]
    assert len(mail) == 1 and mail[0]["body"].count("/q/") == 2
    rows = owner.get("/api/assessments").json()
    assert {a["vendor_name"] for a in rows} == {"CloudCo"} and rows[0]["questions_total"] > 0
    a = db.scalar(select(VendorAssessment).where(VendorAssessment.template_slug == "standard-lite"))
    assert len(a.questions) == rows[[x["template_slug"] for x in rows].index("standard-lite")]["questions_total"]


def test_vendor_answers_choice_and_na_rules(owner, mail):
    vid = _vendor(owner)
    link = owner.post(f"/api/vendors/{vid}/assessments",
                      json={"template_slug": "standard-lite", "email": "sec@cloudco.com"}).json()["link"]
    vendor = make_client()
    info = vendor.get(f"/api/public/assessments/{_token(link)}").json()
    answers = {}
    for q in info["questions"]:
        if q["type"] == "yes_no":
            answers[q["id"]] = {"answer": q.get("good", "yes") or "yes", "comment": ""}
        elif q["type"] == "choice":
            answers[q["id"]] = {"answer": q["options"][0], "comment": ""}
        else:
            answers[q["id"]] = {"answer": "Bengaluru", "comment": ""}
    choice = next((q for q in info["questions"] if q["type"] == "choice"), None)
    if choice:
        bad = {**answers, choice["id"]: {"answer": "Something else", "comment": ""}}
        assert vendor.put(f"/api/public/assessments/{_token(link)}", json={"answers": bad}).status_code == 422
    scored = next(q for q in info["questions"] if q["type"] == "yes_no" and q.get("weight"))
    na = {**answers, scored["id"]: {"answer": "na", "comment": ""}}
    r = vendor.post(f"/api/public/assessments/{_token(link)}/submit", json={"answers": na, "respondent_name": "Ravi"})
    assert r.status_code == 400 and "N/A" in r.json()["detail"]
    na[scored["id"]]["comment"] = "We have no offices; fully remote"
    r = vendor.post(f"/api/public/assessments/{_token(link)}/submit", json={"answers": na, "respondent_name": "Ravi"})
    assert r.status_code == 200, r.text
    a = owner.get("/api/assessments").json()[0]
    assert a["status"] == "submitted" and a["score"] == 100
    x = owner.get(f"/api/vendors/{vid}/assessments/{a['id']}/export")
    assert x.status_code == 200 and b"Bengaluru" not in x.content[:4]  # a real xlsx, not text


def test_remind_issues_fresh_link_and_cancel_kills_it(owner, mail):
    vid = _vendor(owner)
    first = owner.post(f"/api/vendors/{vid}/assessments",
                       json={"template_slug": "standard-lite", "email": "sec@cloudco.com"}).json()
    aid, old = first["id"], _token(first["link"])
    r = owner.post(f"/api/assessments/{aid}/remind")
    assert r.status_code == 200 and r.json()["reminders_sent"] == 1
    new = _token(r.json()["link"])
    assert make_client().get(f"/api/public/assessments/{old}").status_code == 404
    assert make_client().get(f"/api/public/assessments/{new}").status_code == 200
    assert owner.post(f"/api/assessments/{aid}/remind").status_code == 429  # not twice in 12 hours
    assert owner.post(f"/api/assessments/{aid}/cancel").json()["status"] == "cancelled"
    assert make_client().get(f"/api/public/assessments/{new}").status_code == 404


def test_auto_reminder_three_days_before_due(owner, mail, db, admin_engine):
    from app.services.reminders import run_reminders

    vid = _vendor(owner)
    owner.post(f"/api/vendors/{vid}/assessments", json={"template_slug": "standard-lite", "email": "s@cloudco.com",
                                                        "expires_days": 3})
    mail.clear()
    run_reminders(db)
    run_reminders(db)
    reminders = [m for m in mail if m["subject"].startswith("Reminder")]
    assert len(reminders) == 1 and "/q/" in reminders[0]["body"]


def test_custom_questionnaire_copy_edit_import_and_isolation(owner, mail):
    c = owner.post("/api/questionnaires", json={"title": "Our SaaS set", "copy_from": "standard-lite"}).json()
    assert c["slug"].startswith("org-") and c["based_on"] == "standard-lite" and c["source"] == "custom"
    qs = c["questions_list"][:3] + [{"section": "Extra", "text": "Do you support SCIM?", "type": "yes_no",
                                     "weight": 1, "good": "yes"},
                                    {"section": "Extra", "text": "Hosting region?", "type": "choice",
                                     "options": ["India", "EU", "US"]}]
    r = owner.put(f"/api/questionnaires/{c['slug']}", json={"title": "Our SaaS set v2", "questions": qs})
    assert r.status_code == 200 and r.json()["questions"] == 5
    bad = qs + [{"text": "Broken choice", "type": "choice", "options": ["only one"]}]
    assert owner.put(f"/api/questionnaires/{c['slug']}", json={"title": "x", "questions": bad}).status_code == 422
    assert owner.put("/api/questionnaires/standard-full", json={"title": "x", "questions": qs}).status_code == 404

    # import from CSV and XLSX
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Domain", "Question", "Type", "Weight", "Expected answer", "Options"])
    w.writerow(["Access", "Is MFA enforced for admins?", "Yes/No", "3", "Yes", ""])
    w.writerow(["Hosting", "Where is data stored?", "", "", "", "India|EU"])
    w.writerow(["", "", "", "", "", ""])
    parsed = owner.post("/api/questionnaires/parse", files={"file": ("q.csv", buf.getvalue().encode())}).json()
    assert [q["type"] for q in parsed["questions"]] == ["yes_no", "choice"]
    assert parsed["questions"][0]["weight"] == 3 and parsed["questions"][1]["options"] == ["India", "EU"]
    wb = Workbook()
    wb.active.append(["Question", "Type"])
    wb.active.append(["Describe your backup approach", "Text"])
    wb.active.append(["=HYPERLINK(\"http://evil\")", "Text"])  # formulas are never evaluated or imported
    out = io.BytesIO()
    wb.save(out)
    parsed = owner.post("/api/questionnaires/parse", files={"file": ("q.xlsx", out.getvalue())}).json()
    assert [q["text"] for q in parsed["questions"]] == ["Describe your backup approach"]
    assert owner.post("/api/questionnaires/parse", files={"file": ("q.pdf", b"%PDF")}).status_code == 422

    # send the custom one; edits afterwards don't change what was sent
    vid = _vendor(owner)
    owner.post(f"/api/vendors/{vid}/assessments", json={"template_slug": c["slug"], "email": "s@cloudco.com"})
    owner.put(f"/api/questionnaires/{c['slug']}", json={"title": "v3", "questions": qs[:1]})
    assert owner.get("/api/assessments").json()[0]["questions_total"] == 5
    owner.delete(f"/api/questionnaires/{c['slug']}")
    assert owner.get("/api/assessments").json()[0]["questions_total"] == 5

    # another company can't see or send it
    other = make_client()
    signup(other, email="o@beta.in", org="Beta")
    verify_email("o@beta.in")
    onboard(other)
    mine = owner.post("/api/questionnaires", json={"title": "Private", "copy_from": "standard-lite"}).json()
    assert other.get(f"/api/questionnaires/{mine['slug']}").status_code == 404
    assert mine["slug"] not in {t["slug"] for t in other.get("/api/questionnaires").json()}


def test_exported_answers_neutralise_formulas(owner, mail):
    vid = _vendor(owner)
    link = owner.post(f"/api/vendors/{vid}/assessments",
                      json={"template_slug": "vendor-security-baseline", "email": "s@cloudco.com"}).json()["link"]
    vendor = make_client()
    info = vendor.get(f"/api/public/assessments/{_token(link)}").json()
    answers = {q["id"]: {"answer": "yes" if q["type"] == "yes_no" else "=cmd|' /C calc'!A0", "comment": ""}
               for q in info["questions"]}
    vendor.post(f"/api/public/assessments/{_token(link)}/submit", json={"answers": answers, "respondent_name": "Ravi"})
    a = owner.get("/api/assessments").json()[0]
    ws = load_workbook(io.BytesIO(owner.get(f"/api/vendors/{vid}/assessments/{a['id']}/export").content)).active
    cells = [c for row in ws.iter_rows(values_only=True) for c in row if isinstance(c, str) and "cmd|" in c]
    assert cells and all(c.startswith("'") for c in cells)


# ================================================================ training


def _roster(db, org_id, people):
    for email, name, dept, joined in people:
        db.add(Person(org_id=org_id, email=email, full_name=name, department=dept, join_date=joined, status="active"))
    db.commit()


def test_department_assignment_new_joiner_due_dates_and_roster(owner, db):
    org = db.scalar(select(Organization))
    member = _join(owner, "dev@acme.in", name="Dev Patel")
    _roster(db, org.id, [("dev@acme.in", "Dev Patel", "Engineering", date.today() - timedelta(days=400)),
                         ("fin@acme.in", "Fiona Rao", "Finance", date.today() - timedelta(days=5))])
    courses = {c["slug"]: c for c in owner.get("/api/training/courses").json()}
    assert len(courses) >= 12 and courses["india-scams"]["category"] == "Foundations"
    # secure development is not yet required; make it required for Engineering only
    r = owner.put("/api/training/assignments/secure-development",
                  json={"required": True, "renew_months": 12, "due_days": 30, "departments": ["Engineering"]})
    assert r.status_code == 200
    mine = {c["slug"]: c for c in member.get("/api/training/courses").json()}
    assert mine["secure-development"]["required"] and mine["secure-development"]["my_status"] == "due"
    report = owner.get("/api/training/report").json()
    people = {p["email"]: p for p in report["people"]}
    assert "secure-development" in people["dev@acme.in"]["courses"]
    assert "secure-development" not in people["fin@acme.in"]["courses"]
    # current staff get the window from when the course became required; new joiners from their joining date
    db.execute(text("UPDATE training_assignments SET required_since = :d WHERE course_slug = 'security-essentials'"),
               {"d": date.today() - timedelta(days=60)})
    db.commit()
    people = {p["email"]: p for p in owner.get("/api/training/report").json()["people"]}
    fin_due = date.fromisoformat(people["fin@acme.in"]["due"]["security-essentials"])
    assert fin_due == date.today() - timedelta(days=5) + timedelta(days=30)
    assert people["dev@acme.in"]["courses"]["security-essentials"] == "overdue"
    assert people["fin@acme.in"]["has_account"] is False and report["not_invited"] == 1
    assert {d["department"] for d in report["departments"]} >= {"Engineering", "Finance"}
    exported = owner.get("/api/training/report.csv").text
    assert "fin@acme.in" in exported and "secure-development" in exported


def test_invite_roster_people_without_accounts(owner, db, mail):
    org = db.scalar(select(Organization))
    _roster(db, org.id, [("new1@acme.in", "New One", "Sales", date.today()),
                         ("new2@acme.in", "New Two", "Sales", date.today())])
    assert owner.post("/api/training/invite-roster").json() == {"invited": 2}
    assert owner.post("/api/training/invite-roster").json() == {"invited": 0}  # already invited
    assert {m["to"][0] for m in mail} == {"new1@acme.in", "new2@acme.in"}


def test_take_course_get_certificate_and_explanations(owner):
    course = owner.get("/api/training/courses/passwords-mfa").json()
    assert "answer" not in json.dumps(course["quiz"])
    assert owner.get("/api/training/courses/passwords-mfa/certificate").status_code == 404
    from app.services.content import read_yaml_dir

    key = {c["slug"]: c for c in read_yaml_dir("training")}["passwords-mfa"]["quiz"]
    r = owner.post("/api/training/courses/passwords-mfa/submit", json={"answers": [q["answer"] for q in key]}).json()
    assert r["passed"] and r["results"][0]["explain"]
    cert = owner.get("/api/training/courses/passwords-mfa/certificate").json()
    assert cert["name"] == "Asha Rao" and cert["score"] == 100 and cert["org_name"] == "Acme"
    assert date.fromisoformat(cert["valid_until"]) >= date.today() + timedelta(days=359)
    scen = owner.get("/api/training/courses/india-scams").json()["scenarios"]
    assert scen and {s["verdict"] for s in scen} <= {"phish", "legit"}


def test_company_course_draft_publish_and_take(owner):
    member = _join(owner, "m@acme.in")
    body = {"title": "Acme client data rules", "summary": "For the Acme project", "body_md": "## Rules\n\nNo exports.",
            "video_url": "http://insecure.example", "quiz": [{"q": "May you export client data?",
                                                              "options": ["Yes", "No"], "answer": 1}]}
    assert owner.post("/api/training/custom", json=body).status_code == 422  # https only
    body["video_url"] = "https://videos.example/abc"
    assert owner.post("/api/training/custom", json={**body, "quiz": [{"q": "Bad?", "options": ["a", "b"],
                                                                       "answer": 5}]}).status_code == 422
    c = owner.post("/api/training/custom", json=body).json()
    assert not c["published"]
    assert member.get(f"/api/training/courses/{c['slug']}").status_code == 404  # drafts hidden from staff
    assert member.post("/api/training/custom", json=body).status_code == 403
    owner.put(f"/api/training/custom/{c['slug']}", json={**body, "published": True})
    got = member.get(f"/api/training/courses/{c['slug']}").json()
    assert got["video_url"] == "https://videos.example/abc" and got["quiz"][0]["options"] == ["Yes", "No"]
    assert member.post(f"/api/training/courses/{c['slug']}/submit", json={"answers": [1]}).json()["passed"]
    owner.put(f"/api/training/assignments/{c['slug']}", json={"required": True, "renew_months": 12, "due_days": 14,
                                                              "departments": []})
    people = {p["email"]: p for p in owner.get("/api/training/report").json()["people"]}
    assert people["m@acme.in"]["courses"][c["slug"]] == "passed"
    assert people["owner@acme.in"]["courses"][c["slug"]] == "due"


def test_phishing_campaign_only_company_domains_click_tracking_and_enrollment(owner, db, mail):
    org = db.scalar(select(Organization))
    _join(owner, "m@acme.in", name="Mira Shah")
    _roster(db, org.id, [("m@acme.in", "Mira Shah", "Sales", date.today() - timedelta(days=100)),
                         ("contractor@gmail.com", "Outside Person", "Sales", date.today())])
    tpls = {t["slug"] for t in owner.get("/api/training/phishing/templates").json()}
    assert {"password-expiry", "upi-refund", "ceo-request"} <= tpls
    c = owner.post("/api/training/phishing/campaigns", json={"name": "Q4 test", "template_slug": "upi-refund",
                                                             "departments": ["Sales"]}).json()
    assert c["status"] == "draft" and c["eligible"] == 1  # gmail address excluded, owner not in Sales
    r = owner.post(f"/api/training/phishing/campaigns/{c['id']}/launch")
    assert r.status_code == 200, r.text
    assert owner.post(f"/api/training/phishing/campaigns/{c['id']}/launch").status_code == 400
    phish = [m for m in mail if m.get("from_name")]
    assert [m["to"] for m in phish] == [["m@acme.in"]] and phish[0]["from_name"] == "Payments Team"
    token = phish[0]["body"].split("/l/")[1].split()[0]

    anon = make_client()
    landing = anon.get(f"/api/public/phish/{token}").json()
    assert landing["org_name"] == "Acme" and landing["red_flags"]
    detail = owner.get(f"/api/training/phishing/campaigns/{c['id']}").json()
    assert detail["results"]["clicked"] == 0  # opening the page (or a link scanner) isn't a click
    assert anon.post(f"/api/public/phish/{token}/click").status_code == 204
    anon.post(f"/api/public/phish/{token}/click")
    detail = owner.get(f"/api/training/phishing/campaigns/{c['id']}").json()
    assert detail["results"]["clicked"] == 1 and detail["click_rate"] == 100
    people = {p["email"]: p for p in owner.get("/api/training/report").json()["people"]}
    assert people["m@acme.in"]["courses"]["phishing"] == "due"
    assert anon.get("/api/public/phish/not-a-token").status_code == 404

    # members can't see campaigns; other companies can't either
    member = make_client()
    member.post("/api/auth/login", json={"email": "m@acme.in", "password": "Saffron-Bicycle-Ladder-31"})
    assert member.get("/api/training/phishing/campaigns").status_code == 403
    other = make_client()
    signup(other, email="o@beta.in", org="Beta")
    verify_email("o@beta.in")
    onboard(other)
    assert other.get(f"/api/training/phishing/campaigns/{c['id']}").status_code == 404
    assert db.scalar(select(PhishingTarget)).clicked_at is not None


def test_enrollment_needs_a_fresh_completion(owner, db):
    from app.services import training as tr

    org = db.scalar(select(Organization))
    from app.services.content import read_yaml_dir

    key = {c["slug"]: c for c in read_yaml_dir("training")}["phishing"]["quiz"]
    owner.post("/api/training/courses/phishing/submit", json={"answers": [q["answer"] for q in key]})
    people = {p["email"]: p for p in owner.get("/api/training/report").json()["people"]}
    assert people["owner@acme.in"]["courses"]["phishing"] == "passed"
    tr.enroll(db, org.id, "owner@acme.in", "phishing", "Clicked a simulation")
    db.commit()
    people = {p["email"]: p for p in owner.get("/api/training/report").json()["people"]}
    assert people["owner@acme.in"]["courses"]["phishing"] == "due"
    a = db.scalar(select(TrainingAssignment).where(TrainingAssignment.course_slug == "phishing"))
    assert a.required_since is not None
