"""Consent records, security training and vendor due diligence."""
import io
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, text

from app.services import notify
from tests.conftest import make_client, onboard, signup, verify_email

NOTICE = {
    "key": "signup", "title": "Account sign-up", "body_md": "We use your data to run your account.",
    "purposes": [{"id": "account", "label": "Run your account", "required": True},
                 {"id": "marketing", "label": "Product news by email"}],
}


def _publish_notice(client) -> dict:
    n = client.post("/api/consent/notices", json=NOTICE)
    assert n.status_code == 201, n.text
    r = client.post(f"/api/consent/notices/{n.json()['id']}/publish")
    assert r.status_code == 200, r.text
    return r.json()


def _api_key(client, scopes) -> str:
    return client.post("/api/org/api-keys", json={"name": "site", "scopes": scopes}).json()["secret"]


# ================================================================ consent


def test_consent_api_records_idempotent_events_and_tracks_state(owner):
    _publish_notice(owner)
    key = _api_key(owner, ["consent:write", "consent:read"])
    machine = make_client()
    h = {"Authorization": f"Bearer {key}"}
    ev = {"event_id": "e-1", "principal_id": "user-42", "notice_key": "signup", "action": "granted",
          "purposes": ["account", "marketing"], "source": "web", "metadata": {"ip_country": "IN"}}
    r = machine.post("/api/v1/consent/events", json=ev, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["notice_version"] == 1 and r.json()["metadata"] == {"ip_country": "IN"}
    assert machine.post("/api/v1/consent/events", json=ev, headers=h).status_code == 200  # replay is a no-op

    # required purposes are enforced, unknown purposes rejected
    bad = {**ev, "event_id": "e-2", "purposes": ["marketing"]}
    assert machine.post("/api/v1/consent/events", json=bad, headers=h).status_code == 422
    bad = {**ev, "event_id": "e-3", "purposes": ["account", "selling"]}
    assert machine.post("/api/v1/consent/events", json=bad, headers=h).status_code == 422

    withdraw = {"event_id": "e-4", "principal_id": "user-42", "notice_key": "signup", "action": "withdrawn",
                "purposes": ["marketing"]}
    assert machine.post("/api/v1/consent/events", json=withdraw, headers=h).status_code == 201
    state = machine.get("/api/v1/consent/principals/user-42", headers=h).json()
    assert state["consents"]["signup"]["purposes"] == ["account"]
    changes = machine.get("/api/v1/consent/events?action=withdrawn", headers=h).json()
    assert [e["event_id"] for e in changes["events"]] == ["e-4"]

    summary = owner.get("/api/consent/summary").json()
    assert summary["granted_30d"] == 1 and summary["withdrawn_30d"] == 1 and summary["principals"] == 1
    csv = owner.get("/api/consent/export")
    assert csv.status_code == 200 and "user-42" in csv.text


def test_consent_api_key_scopes_and_auth(owner):
    _publish_notice(owner)
    read_only = _api_key(owner, ["consent:read"])
    machine = make_client()
    ev = {"event_id": "x", "principal_id": "p", "notice_key": "signup", "action": "granted", "purposes": ["account"]}
    assert machine.post("/api/v1/consent/events", json=ev).status_code == 401
    assert machine.post("/api/v1/consent/events", json=ev,
                        headers={"Authorization": "Bearer anp_wrong"}).status_code == 401
    assert machine.post("/api/v1/consent/events", json=ev,
                        headers={"Authorization": f"Bearer {read_only}"}).status_code == 403


def test_consent_log_is_append_only_and_tenant_isolated(owner, admin_engine):
    _publish_notice(owner)
    owner.post("/api/consent/events", json={"event_id": "m-1", "principal_id": "p-1", "notice_key": "signup",
                                            "action": "granted", "purposes": ["account"], "source": "paper"})
    other = make_client()
    signup(other, email="cfo@other.in", org="Other")
    verify_email("cfo@other.in")
    onboard(other)
    assert other.get("/api/consent/events").json() == []
    assert other.get("/api/consent/principals/p-1").json()["consents"] == {}

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        db.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
        try:
            db.execute(text("UPDATE consent_events SET action = 'withdrawn'"))
            raise AssertionError("runtime role must not update consent records")
        except Exception as e:  # noqa: BLE001 - asserting on the database error
            assert "permission denied" in str(e)
    finally:
        db.rollback()
        db.close()


def test_published_notice_is_immutable_and_versioned(owner):
    n = _publish_notice(owner)
    assert owner.put(f"/api/consent/notices/{n['id']}", json=NOTICE).status_code == 400
    v2 = owner.post("/api/consent/notices", json={**NOTICE, "title": "Account sign-up (2027)"}).json()
    assert v2["version"] == 2
    owner.post(f"/api/consent/notices/{v2['id']}/publish")
    statuses = {x["version"]: x["status"] for x in owner.get("/api/consent/notices").json()}
    assert statuses == {1: "retired", 2: "published"}


def test_consent_platform_check(owner, db):
    from app.models import Organization, TestResult
    from app.services.platform_checks import run_feature_checks

    _publish_notice(owner)
    org = db.scalar(select(Organization))
    run_feature_checks(db, org, force=True)
    db.commit()
    r = db.scalar(select(TestResult).where(TestResult.test_key == "platform.consent_capture"))
    assert r.status == "fail"
    owner.post("/api/consent/events", json={"event_id": "m-1", "principal_id": "p-1", "notice_key": "signup",
                                            "action": "granted", "purposes": ["account"], "source": "paper"})
    run_feature_checks(db, org, force=True)
    db.commit()
    latest = db.scalars(select(TestResult).where(TestResult.test_key == "platform.consent_capture")
                        .order_by(TestResult.run_at.desc())).first()
    assert latest.status == "pass"


# ================================================================ training


def test_training_quiz_hides_answers_and_scores_on_server(owner):
    courses = owner.get("/api/training/courses").json()
    assert {c["slug"] for c in courses} >= {"security-essentials", "dpdp-basics", "phishing"}
    assert all(c["my_status"] == "due" for c in courses if c["required"])
    course = owner.get("/api/training/courses/phishing").json()
    assert course["quiz"] and all("answer" not in q for q in course["quiz"])

    from app.services.content import read_yaml_dir

    answers = [q["answer"] for q in next(c for c in read_yaml_dir("training") if c["slug"] == "phishing")["quiz"]]
    wrong = owner.post("/api/training/courses/phishing/submit",
                       json={"answers": [(a + 1) % len(course["quiz"][i]["options"]) for i, a in enumerate(answers)]})
    assert wrong.json()["passed"] is False
    statuses = {c["slug"]: c["my_status"] for c in owner.get("/api/training/courses").json()}
    assert statuses["phishing"] == "failed"
    right = owner.post("/api/training/courses/phishing/submit", json={"answers": answers})
    assert right.json() == {**right.json(), "score": 100, "passed": True}
    statuses = {c["slug"]: c["my_status"] for c in owner.get("/api/training/courses").json()}
    assert statuses["phishing"] == "passed"
    assert owner.post("/api/training/courses/phishing/submit", json={"answers": [0]}).status_code == 400


def test_training_report_import_and_check(owner, db):
    from app.models import Organization, TestResult
    from app.services.platform_checks import run_feature_checks

    report = owner.get("/api/training/report").json()
    assert report["completion_percent"] == 0 and report["people"][0]["email"] == "owner@acme.in"
    today = date.today().isoformat()
    csv = "email,course,completed_at,score\n" + "".join(
        f"owner@acme.in,{c},{today},95\n" for c in ("security-essentials", "India's DPDP Act for everyone at work", "phishing")
    ) + "bad-row,nope,,\n"
    r = owner.post("/api/training/import", files={"file": ("lms.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["skipped"] == ["Row 5"]
    org = db.scalar(select(Organization))
    assert r.json()["imported"] == 3
    assert owner.get("/api/training/report").json()["completion_percent"] == 100
    run_feature_checks(db, org, force=True)
    db.commit()
    result = db.scalar(select(TestResult).where(TestResult.test_key == "platform.training_completion"))
    assert result.status == "pass"


def test_training_admin_only_settings(owner):
    owner.post("/api/org/invitations", json={"email": "dev@acme.in", "role": "member"})
    assert owner.put("/api/training/assignments/secure-development",
                     json={"required": True, "renew_months": 12, "due_days": 30}).status_code == 200
    required = owner.get("/api/training/report").json()["required_courses"]
    assert "secure-development" in required


# ================================================================ vendor due diligence


def _vendor(client, **kw) -> dict:
    r = client.post("/api/vendors", json={"name": "Payments Co", "tier": "critical", "is_processor": True, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _all_good(questions):
    return {q["id"]: {"answer": q.get("good", "yes") if q["type"] == "yes_no" else "India"} for q in questions}


def test_vendor_questionnaire_link_flow(owner, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
    v = _vendor(owner)
    r = owner.post(f"/api/vendors/{v['id']}/assessments",
                   json={"template_slug": "vendor-security-baseline", "email": "security@payments.example"})
    assert r.status_code == 201, r.text
    token = r.json()["link"].rsplit("/", 1)[1]
    assert sent and token in sent[0][2]

    vendor = make_client()  # the vendor has no account
    q = vendor.get(f"/api/public/assessments/{token}")
    assert q.status_code == 200 and q.json()["org_name"] == "Acme" and q.json()["vendor_name"] == "Payments Co"
    questions = q.json()["questions"]
    answers = _all_good(questions)
    answers["acc-1"] = {"answer": "no", "comment": "Rolling out next quarter"}  # weight-3 miss
    assert vendor.put(f"/api/public/assessments/{token}",
                      json={"answers": {"acc-1": {"answer": "maybe"}}}).status_code == 422
    assert vendor.put(f"/api/public/assessments/{token}", json={"answers": dict(list(answers.items())[:5])}
                      ).json()["status"] == "in_progress"
    assert vendor.post(f"/api/public/assessments/{token}/submit", json={"answers": {}}).status_code == 400
    up = vendor.post(f"/api/public/assessments/{token}/documents", data={"kind": "iso27001",
                                                                          "valid_until": "2027-03-31"},
                     files={"file": ("cert.pdf", b"%PDF-1.7\n1 0 obj\n", "application/pdf")})
    assert up.status_code == 201, up.text
    done = vendor.post(f"/api/public/assessments/{token}/submit",
                       json={"answers": answers, "respondent_name": "Ravi (CISO)"})
    assert done.status_code == 200, done.text
    assert vendor.put(f"/api/public/assessments/{token}", json={"answers": {}}).status_code == 400

    detail = owner.get(f"/api/vendors/{v['id']}/detail").json()
    a = detail["assessments"][0]
    assert a["status"] == "submitted" and a["score"] >= 85 and a["rating"] == "medium"  # critical miss caps it
    assert detail["documents"][0]["uploaded_via"] == "vendor_portal"
    full = owner.get(f"/api/vendors/{v['id']}/assessments/{a['id']}").json()
    assert full["critical_issues"] == ["acc-1"]

    rv = owner.post(f"/api/vendors/{v['id']}/assessments/{a['id']}/review", json={"notes": "MFA gap accepted"})
    assert rv.status_code == 200 and rv.json()["status"] == "reviewed"
    vendors = {x["id"]: x for x in owner.get("/api/vendors").json()}
    assert vendors[v["id"]]["last_assessed_at"] == date.today().isoformat()
    assert vendors[v["id"]]["next_review_date"] is not None
    controls = owner.get("/api/controls").json()
    ven = next(c for c in controls if c["code"] == "VEN-01")
    ev = owner.get(f"/api/controls/{ven['id']}").json()["evidence"]
    assert any("Payments Co" in e["title"] for e in ev)


def test_vendor_link_is_bound_to_its_org_and_expires(owner, db):
    from app.models import VendorAssessment

    v = _vendor(owner)
    token = owner.post(f"/api/vendors/{v['id']}/assessments",
                       json={"template_slug": "dpdp-processor", "email": "dpo@payments.example"}
                       ).json()["link"].rsplit("/", 1)[1]
    anon = make_client()
    assert anon.get("/api/public/assessments/not-a-real-token").status_code == 404
    a = db.scalar(select(VendorAssessment))
    a.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert anon.get(f"/api/public/assessments/{token}").status_code == 404

    other = make_client()
    signup(other, email="cfo@other.in", org="Other")
    verify_email("cfo@other.in")
    onboard(other)
    assert other.get(f"/api/vendors/{v['id']}/detail").status_code == 404
    assert other.get(f"/api/vendors/{v['id']}/assessments/{a.id}").status_code == 404


def test_vendor_documents_and_expiry_reminders(owner, db):
    from app.models import Notification, Organization
    from app.services.reminders import vendor_document_reminders

    v = _vendor(owner)
    soon = (date.today() + timedelta(days=10)).isoformat()
    r = owner.post(f"/api/vendors/{v['id']}/documents", data={"kind": "soc2", "valid_until": soon},
                   files={"file": ("soc2.pdf", io.BytesIO(b"%PDF-1.7\nreport"), "application/pdf")})
    assert r.status_code == 201, r.text
    assert "SOC 2" in owner.get("/api/vendors").json()[0]["certifications"]
    bad = owner.post(f"/api/vendors/{v['id']}/documents", data={"kind": "soc2"},
                     files={"file": ("soc2.pdf", io.BytesIO(b"MZ\x90\x00 not a pdf"), "application/pdf")})
    assert bad.status_code == 400
    dl = owner.get(f"/api/vendors/{v['id']}/documents/{r.json()['id']}/download")
    assert dl.status_code == 200 and dl.content.startswith(b"%PDF")

    org = db.scalar(select(Organization))
    vendor_document_reminders(db, org, date.today())
    db.commit()
    titles = [n.title for n in db.scalars(select(Notification))]
    assert any("SOC 2" in t and "expires" in t for t in titles)


def test_scoring():
    from app.api.routes.vendor_dd import score_answers

    qs = [{"id": "a", "type": "yes_no", "weight": 3, "good": "yes"},
          {"id": "b", "type": "yes_no", "weight": 1, "good": "no"},
          {"id": "c", "type": "text", "weight": 0}]
    assert score_answers(qs, {"a": {"answer": "yes"}, "b": {"answer": "no"}})[:2] == (100, "low")
    assert score_answers(qs, {"a": {"answer": "no"}, "b": {"answer": "no"}})[:2] == (25, "high")
    assert score_answers(qs, {"a": {"answer": "na"}, "b": {"answer": "no"}})[:2] == (100, "low")
    assert score_answers(qs, {})[0] == 0
