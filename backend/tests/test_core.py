from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import Control, Requirement
from app.services.content import check_content
from tests.conftest import PASSWORD, make_client, onboard, signup


def test_content_is_fully_mapped():
    check_content()


def test_content_loaded(db):
    assert db.scalar(select(func.count()).select_from(Requirement)) == check_content()["requirements"]


def test_signup_login_logout(client):
    me = signup(client)
    assert me["role"] == "owner" and not me["onboarded"]
    assert client.get("/api/auth/me").json()["user"]["email"] == "owner@acme.in"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "owner@acme.in", "password": "nope-nope-nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "OWNER@acme.in", "password": PASSWORD})
    assert r.status_code == 200


def test_duplicate_signup_and_weak_password(client):
    signup(client)
    r = make_client().post("/api/auth/signup", json={"full_name": "X", "email": "owner@acme.in",
                                                     "password": PASSWORD, "org_name": "Y"})
    assert r.status_code == 409
    r = make_client().post("/api/auth/signup", json={"full_name": "X", "email": "x@y.in", "password": "short",
                                                     "org_name": "Y"})
    assert r.status_code == 422


def test_login_rate_limited(client):
    signup(client)
    other = make_client()
    for _ in range(10):
        assert other.post("/api/auth/login", json={"email": "owner@acme.in", "password": "wrong-password"}).status_code == 401
    r = other.post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    assert r.status_code == 429


def test_onboarding_provisions_controls_and_policies(owner, db):
    controls = owner.get("/api/controls").json()
    codes = {c["code"] for c in controls}
    # Conditional controls stay out of scope without the profile flags.
    assert "PRV-11" not in codes and "PRV-12" not in codes and "CIN-01" not in codes
    assert {"GOV-01", "PRV-10", "INC-02", "LOG-03"} <= codes
    assert all(c["health"] == "not_started" for c in controls)
    assert len(owner.get("/api/policies").json()) == 8
    readiness = owner.get("/api/frameworks/readiness").json()
    assert {r["code"] for r in readiness} == {"dpdp", "certin", "iso27001", "soc2"}
    dpdp = next(r for r in readiness if r["code"] == "dpdp")
    assert dpdp["percent"] == 0 and dpdp["not_applicable_requirements"] > 0


def test_profile_flag_adds_conditional_controls(owner):
    r = owner.patch("/api/org", json={"profile": {"processes_children_data": True}})
    assert r.status_code == 200
    assert "PRV-11" in {c["code"] for c in owner.get("/api/controls").json()}


def test_control_health_and_readiness(owner):
    ctl = next(c for c in owner.get("/api/controls").json() if c["code"] == "LOG-03")
    r = owner.patch(f"/api/controls/{ctl['id']}", json={"status": "implemented"})
    assert r.json()["health"] == "needs_evidence"
    r = owner.post(f"/api/controls/{ctl['id']}/evidence",
                   data={"title": "NTP config", "kind": "note", "description": "chrony points to samay1.nic.in"})
    assert r.status_code == 201, r.text
    assert r.json()["valid_until"] is not None
    detail = owner.get(f"/api/controls/{ctl['id']}").json()
    assert detail["control"]["health"] == "passing"
    assert {"CERT-In", "ISO 27001", "SOC 2"} <= set(detail["control"]["frameworks"])
    certin = next(x for x in owner.get("/api/frameworks/readiness").json() if x["code"] == "certin")
    assert certin["met"] == 1
    rows = owner.get("/api/frameworks/certin").json()["requirements"]
    assert next(x for x in rows if x["ref"] == "(i)")["status"] == "met"


def test_not_applicable_requires_justification(owner):
    ctl = owner.get("/api/controls").json()[0]
    assert owner.patch(f"/api/controls/{ctl['id']}", json={"status": "not_applicable"}).status_code == 400
    r = owner.patch(f"/api/controls/{ctl['id']}", json={"status": "not_applicable", "na_justification": "No office"})
    assert r.json()["health"] == "not_applicable"


def test_evidence_file_upload_and_download(owner):
    ctl = owner.get("/api/controls").json()[0]
    r = owner.post(f"/api/controls/{ctl['id']}/evidence", data={"title": "Policy", "kind": "file"},
                   files={"file": ("policy.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 201, r.text
    ev = r.json()
    d = owner.get(f"/api/evidence/{ev['id']}/download")
    assert d.status_code == 200 and d.content == b"%PDF-1.4 test"
    bad = owner.post(f"/api/controls/{ctl['id']}/evidence", data={"title": "x", "kind": "file"},
                     files={"file": ("run.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400


def test_tenant_isolation():
    a, b = make_client(), make_client()
    signup(a, "a@a.in", "Org A")
    onboard(a)
    signup(b, "b@b.in", "Org B")
    onboard(b)
    ctl_a = a.get("/api/controls").json()[0]
    ev = a.post(f"/api/controls/{ctl_a['id']}/evidence", data={"title": "x", "kind": "note", "description": "y"}).json()
    risk = a.post("/api/risks", json={"title": "Laptop theft"}).json()
    assert b.get(f"/api/controls/{ctl_a['id']}").status_code == 404
    assert b.patch(f"/api/controls/{ctl_a['id']}", json={"status": "implemented"}).status_code == 404
    assert b.get(f"/api/evidence/{ev['id']}/download").status_code == 404
    assert b.delete(f"/api/evidence/{ev['id']}").status_code == 404
    assert b.put(f"/api/risks/{risk['id']}", json={"title": "hacked"}).status_code == 404
    assert all(r["id"] != risk["id"] for r in b.get("/api/risks").json())
    # Cannot assign a control in org B to a user from org A.
    a_user = a.get("/api/auth/me").json()["user"]["id"]
    ctl_b = b.get("/api/controls").json()[0]
    assert b.patch(f"/api/controls/{ctl_b['id']}", json={"owner_id": a_user}).status_code == 400
    # Cannot switch into an org you are not a member of.
    org_a = a.get("/api/auth/me").json()["org_id"]
    assert b.post("/api/auth/switch-org", json={"org_id": org_a}).status_code == 403


def test_invitation_and_roles(owner):
    inv = owner.post("/api/org/invitations", json={"email": "aud@acme.in", "role": "auditor", "access_days": 30}).json()
    token = inv["invite_url"].rsplit("/", 1)[1]
    auditor = make_client()
    assert auditor.get(f"/api/auth/invitations/{token}").json()["org_name"] == "Acme"
    r = auditor.post("/api/auth/invitations/accept",
                     json={"token": token, "full_name": "Auditor", "password": "Quartz-Lantern-Harbor-42"})
    assert r.status_code == 200 and r.json()["role"] == "auditor"
    ctl = auditor.get("/api/controls").json()[0]
    assert auditor.patch(f"/api/controls/{ctl['id']}", json={"status": "implemented"}).status_code == 403
    assert auditor.post("/api/risks", json={"title": "x"}).status_code == 403
    # Invitation cannot be reused.
    assert make_client().post("/api/auth/invitations/accept", json={
        "token": token, "full_name": "X", "password": "Quartz-Lantern-Harbor-42"}).status_code == 404
    # Last owner cannot be demoted.
    me = owner.get("/api/auth/me").json()["user"]["id"]
    assert owner.patch(f"/api/org/members/{me}", json={"role": "member"}).status_code == 400


def test_policy_approval_creates_evidence_and_versions(owner):
    policy = next(p for p in owner.get("/api/policies").json() if p["slug"] == "information-security-policy")
    assert "Acme" in policy["body_md"] and "{{company}}" not in policy["body_md"]
    r = owner.post(f"/api/policies/{policy['id']}/approve")
    assert r.json()["status"] == "approved" and r.json()["review_due"]
    gov01 = next(c for c in owner.get("/api/controls").json() if c["code"] == "GOV-01")
    assert gov01["valid_evidence"] == 1
    assert owner.post(f"/api/policies/{policy['id']}/acknowledge").json()["acknowledged_by_me"]
    r = owner.patch(f"/api/policies/{policy['id']}", json={"body_md": policy["body_md"] + "\nUpdated."})
    assert r.json()["version"] == 2 and r.json()["status"] == "draft"
    assert not r.json()["acknowledged_by_me"]


def test_rights_request_deadlines(owner):
    received = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
    r = owner.post("/api/dpdp/requests", json={"request_type": "erasure", "requester_name": "Ravi",
                                               "requester_email": "ravi@example.com",
                                               "received_at": received.isoformat()}).json()
    assert r["number"] == 1
    assert datetime.fromisoformat(r["due_at"]) == received + timedelta(days=30)
    assert datetime.fromisoformat(r["legal_due_at"]) == received + timedelta(days=90)
    done = owner.patch(f"/api/dpdp/requests/{r['id']}", json={"status": "completed"}).json()
    assert done["closed_at"]


def test_incident_clocks(owner):
    detected = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
    i = owner.post("/api/incidents", json={"title": "Exposed bucket", "severity": "sev1",
                                           "detected_at": detected.isoformat(), "certin_reportable": True,
                                           "personal_data_breach": True}).json()
    assert datetime.fromisoformat(i["certin_due_at"]) == detected + timedelta(hours=6)
    assert datetime.fromisoformat(i["dpb_due_at"]) == detected + timedelta(hours=72)
    kinds = {d["kind"] for d in owner.get("/api/dashboard").json()["deadlines"]}
    assert {"certin", "dpb", "principals"} <= kinds
    i = owner.patch(f"/api/incidents/{i['id']}", json={"personal_data_breach": False}).json()
    assert i["dpb_due_at"] is None
    bad = owner.post("/api/incidents", json={"title": "x", "detected_at": "2026-10-05T09:00:00"})
    assert bad.status_code == 422


def test_dashboard_and_audit_log(owner):
    d = owner.get("/api/dashboard").json()
    assert d["total_controls"] > 80 and len(d["readiness"]) == 4
    log = owner.get("/api/org/audit-log").json()
    assert any(e["action"] == "org.onboarded" for e in log)


def test_cross_origin_write_blocked(owner):
    r = owner.post("/api/risks", json={"title": "x"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_custom_control(owner, db):
    r = owner.post("/api/controls", json={"code": "CUS-01", "title": "Custom check"})
    assert r.status_code == 201
    assert owner.post("/api/controls", json={"code": "CUS-01", "title": "dup"}).status_code == 409
    assert db.scalar(select(Control).where(Control.code == "CUS-01")) is not None
