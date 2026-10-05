import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select, text

from app.integrations.google_workspace import GoogleWorkspaceConnector
from app.integrations.keka import KekaConnector
from app.integrations.microsoft365 import Microsoft365Connector
from app.models import (
    Account,
    Control,
    DataAsset,
    Evidence,
    Incident,
    Integration,
    Notification,
    Organization,
    RightsRequest,
    Task,
    TestResult,
)
from app.security import encrypt_json
from app.services import notify
from app.services.integrations import sync_integration
from app.services.people import infer_status, parse_csv
from app.services.reminders import run_reminders
from tests.conftest import make_client, onboard, signup


@pytest.fixture(autouse=True)
def reset_rate_limits():
    from app import ratelimit

    ratelimit.store().clear()
    yield


# ---------------------------------------------------------------- fake connectors


def gws_users(suspend_leaver=False):
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    old = (now - timedelta(days=200)).isoformat().replace("+00:00", "Z")
    return [
        {"id": "1", "primaryEmail": "asha@acme.in", "name": {"fullName": "Asha Rao"}, "isAdmin": True,
         "isEnrolledIn2Sv": True, "isEnforcedIn2Sv": True, "lastLoginTime": recent, "creationTime": old},
        {"id": "2", "primaryEmail": "ravi@acme.in", "name": {"fullName": "Ravi K"}, "isAdmin": False,
         "isEnrolledIn2Sv": False, "isEnforcedIn2Sv": True, "lastLoginTime": recent, "creationTime": old},
        {"id": "3", "primaryEmail": "leaver@acme.in", "name": {"fullName": "Lee Ver"}, "isAdmin": False,
         "isEnrolledIn2Sv": True, "isEnforcedIn2Sv": True, "lastLoginTime": old, "creationTime": old,
         "suspended": suspend_leaver},
    ]


def gws_connector(users):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"users": users})

    return GoogleWorkspaceConnector({"admin_email": "asha@acme.in", "max_admins": "2"}, {},
                                    client=httpx.Client(transport=httpx.MockTransport(handler)), token="test-token")


def test_google_workspace_checks_and_accounts():
    c = gws_connector(gws_users())
    results = {r.key: r for r in c.run()}
    assert results["gws.2sv_enforced"].status == "pass"
    assert results["gws.2sv_enrolled"].status == "fail" and results["gws.2sv_enrolled"].details["users"] == ["ravi@acme.in"]
    assert results["gws.admin_count"].status == "pass"
    assert results["gws.inactive_users"].status == "fail"
    accounts = c.list_accounts()
    assert {a.email for a in accounts} == {"asha@acme.in", "ravi@acme.in", "leaver@acme.in"}
    assert next(a for a in accounts if a.email == "asha@acme.in").is_admin


def test_microsoft365_checks_and_accounts():
    def handler(request: httpx.Request) -> httpx.Response:
        p = request.url.path
        if "oauth2/v2.0/token" in p:
            assert request.url.host == "login.microsoftonline.com"
            return httpx.Response(200, json={"access_token": "tok"})
        if p.endswith("/identitySecurityDefaultsEnforcementPolicy"):
            return httpx.Response(200, json={"isEnabled": False})
        if p.endswith("/conditionalAccess/policies"):
            return httpx.Response(200, json={"value": [{
                "displayName": "Require MFA", "state": "enabled",
                "conditions": {"users": {"includeUsers": ["All"]}},
                "grantControls": {"builtInControls": ["mfa"]}}]})
        if p.endswith("/userRegistrationDetails"):
            return httpx.Response(200, json={"value": [
                {"id": "u1", "userPrincipalName": "a@acme.in", "isMfaRegistered": True, "userType": "member"},
                {"id": "u2", "userPrincipalName": "b@acme.in", "isMfaRegistered": False, "userType": "member"}]})
        if "directoryRoles" in p:
            return httpx.Response(200, json={"value": [{"id": "u1"}]})
        if p.endswith("/users"):
            return httpx.Response(200, json={"value": [
                {"id": "u1", "displayName": "A", "mail": "a@acme.in", "accountEnabled": True},
                {"id": "u2", "displayName": "B", "userPrincipalName": "B@acme.in", "accountEnabled": False}]})
        return httpx.Response(404)

    c = Microsoft365Connector({"tenant_id": "t", "client_id": "c"}, {"client_secret": "s"},
                              client=httpx.Client(transport=httpx.MockTransport(handler)))
    c.verify()
    results = {r.key: r for r in c.run()}
    assert results["m365.mfa_policy"].status == "pass" and "Require MFA" in results["m365.mfa_policy"].summary
    assert results["m365.mfa_registered"].status == "fail"
    assert results["m365.global_admins"].status == "pass"
    accounts = {a.external_id: a for a in c.list_accounts()}
    assert accounts["u1"].is_admin and accounts["u1"].mfa_enabled is True
    assert accounts["u2"].email == "b@acme.in" and not accounts["u2"].is_active


def test_keka_mapping_and_paging():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.keka.com":
            form = dict(x.split("=") for x in request.content.decode().split("&"))
            assert form["grant_type"] == "kekaapi" and form["scope"] == "kekaapi" and form["api_key"] == "k"
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        calls.append(dict(request.url.params))
        if request.url.params.get("employmentStatus") == "Relieved":
            return httpx.Response(200, json={"data": [
                {"id": "e2", "email": "Old@Acme.in", "firstName": "Old", "lastName": "Timer",
                 "employmentStatus": "Relieved", "exitDate": "2026-01-31T00:00:00"}], "totalPages": 1})
        return httpx.Response(200, json={"data": [
            {"id": "e1", "email": "new@acme.in", "displayName": "New Joiner", "employeeNumber": "A-1",
             "jobTitle": {"title": "Engineer"}, "reportsTo": {"email": "Boss@acme.in"},
             "joiningDate": "2026-09-01T00:00:00", "employmentStatus": "Working"}], "totalPages": 1})

    c = KekaConnector({"domain": "acme.keka.com", "client_id": "c"}, {"client_secret": "s", "api_key": "k"},
                      client=httpx.Client(transport=httpx.MockTransport(handler)))
    people = {p.email: p for p in c.list_people()}
    assert people["new@acme.in"].manager_email == "boss@acme.in" and people["new@acme.in"].title == "Engineer"
    assert people["new@acme.in"].status == "active" and people["new@acme.in"].join_date == date(2026, 9, 1)
    assert people["old@acme.in"].status == "exited" and people["old@acme.in"].exit_date == date(2026, 1, 31)


def test_csv_roster_parsing():
    content = (
        "Employee Code,Employee Name,Official Email ID,Designation,Reporting Manager Email,Employment Status,"
        "Date of Joining,Last Working Day\n"
        "E1,Asha Rao,ASHA@acme.in,CTO,,Active,01-04-2024,\n"
        "E2,Lee Ver,leaver@acme.in,Engineer,asha@acme.in,Relieved,15/06/2025,30-Sep-2026\n"
        "E3,No Email,,Engineer,,Active,,\n"
        "E4,Bad,not-an-email,Engineer,,Active,,\n"
    ).encode()
    records, warnings = parse_csv(content)
    by = {r.email: r for r in records}
    assert set(by) == {"asha@acme.in", "leaver@acme.in"}
    assert by["leaver@acme.in"].status == "exited" and by["leaver@acme.in"].exit_date == date(2026, 9, 30)
    assert by["leaver@acme.in"].manager_email == "asha@acme.in" and by["asha@acme.in"].join_date == date(2024, 4, 1)
    assert any("not-an-email" in w for w in warnings)
    assert infer_status("Active", date.today() - timedelta(days=1)) == "exited"
    assert infer_status("Active", date.today() + timedelta(days=10)) == "active"


# ---------------------------------------------------------------- leaver check + access review


def _connect_fake_google(db, monkeypatch, users_fn):
    org = db.scalar(select(Organization))
    integ = Integration(org_id=org.id, provider="google_workspace", config={"admin_email": "asha@acme.in"},
                        secret_encrypted=encrypt_json({}))
    db.add(integ)
    db.commit()
    from app.services import integrations as svc

    monkeypatch.setattr(svc, "build_connector", lambda i: gws_connector(users_fn()))
    return integ


ROSTER = (
    "Email,Name,Manager email,Status,Exit date\n"
    "asha@acme.in,Asha Rao,,Active,\n"
    "ravi@acme.in,Ravi K,mgr@acme.in,Active,\n"
    "leaver@acme.in,Lee Ver,mgr@acme.in,Relieved,2026-01-15\n"
)


def test_leaver_check_fails_then_passes_when_account_suspended(owner, db, monkeypatch):
    r = owner.post("/api/people/upload", files={"file": ("people.csv", ROSTER.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["created"] == 3 and r.json()["exited"] == 1
    suspended = {"value": False}
    integ = _connect_fake_google(db, monkeypatch, lambda: gws_users(suspend_leaver=suspended["value"]))

    sync_integration(db, integ)
    leaver = db.scalar(select(TestResult).where(TestResult.test_key == "platform.leaver_access")
                       .order_by(TestResult.run_at.desc()))
    assert leaver.status == "fail" and "leaver@acme.in" in leaver.details["summary"]
    task = db.scalar(select(Task).where(Task.source == "test:platform.leaver_access"))
    assert task.status == "open"
    assert owner.get("/api/people/leavers-with-access").json()["findings"][0]["email"] == "leaver@acme.in"
    assert db.scalar(select(Notification).where(Notification.event == "check_failed"))  # alert queued
    people = {p["email"]: p for p in owner.get("/api/people").json()}
    assert people["leaver@acme.in"]["accounts"][0]["system"] == "Google Workspace"

    suspended["value"] = True
    sync_integration(db, integ)
    db.refresh(task)
    assert task.status == "done"
    acc02 = next(c for c in owner.get("/api/controls").json() if c["code"] == "ACC-02")
    assert acc02["health"] != "failing"


def test_access_review_flow(owner, db, monkeypatch):
    # The manager is a workspace member, so their reports' accounts are routed to them.
    inv = owner.post("/api/org/invitations", json={"email": "mgr@acme.in", "role": "member"}).json()
    mgr = make_client()
    mgr.post("/api/auth/invitations/accept", json={"token": inv["invite_url"].rsplit("/", 1)[1],
                                                   "full_name": "Manager", "password": "Copper-Kettle-Meadow-58"})
    owner.post("/api/people/upload", files={"file": ("people.csv", ROSTER.encode(), "text/csv")})
    integ = _connect_fake_google(db, monkeypatch, lambda: gws_users())
    sync_integration(db, integ)

    avail = owner.get("/api/access-reviews").json()["available_systems"]
    assert avail == [{"provider": "google_workspace", "name": "Google Workspace", "accounts": 3}]
    rid = owner.post("/api/access-reviews", json={"title": "Q4 review", "providers": ["google_workspace"]}).json()["id"]
    detail = mgr.get(f"/api/access-reviews/{rid}").json()
    assert detail["total"] == 3 and detail["my_pending"] == 2  # ravi + leaver report to mgr
    items = {i["email"]: i for i in detail["items"]}
    assert items["leaver@acme.in"]["person_status"] == "exited" and items["leaver@acme.in"]["can_decide"]
    assert not items["asha@acme.in"]["can_decide"]  # not assigned to mgr

    url = f"/api/access-reviews/{rid}/items"
    assert mgr.patch(f"{url}/{items['leaver@acme.in']['id']}", json={"decision": "revoke"}).status_code == 400
    assert mgr.patch(f"{url}/{items['leaver@acme.in']['id']}", json={"decision": "revoke", "note": "Left in Jan"}).status_code == 200
    assert mgr.patch(f"{url}/{items['asha@acme.in']['id']}", json={"decision": "keep"}).status_code == 403
    removal = db.scalar(select(Task).where(Task.source == f"review-item:{items['leaver@acme.in']['id']}"))
    assert removal.status == "open" and removal.priority == "high"

    assert owner.post(f"/api/access-reviews/{rid}/complete").status_code == 400  # still pending
    mgr.patch(f"{url}/{items['ravi@acme.in']['id']}", json={"decision": "keep"})
    owner.patch(f"{url}/{items['asha@acme.in']['id']}", json={"decision": "keep"})

    # Account removed in Google: the next sync verifies the removal and closes the task.
    monkeypatch.setattr("app.services.integrations.build_connector",
                        lambda i: gws_connector([u for u in gws_users() if u["id"] != "3"]))
    sync_integration(db, integ)
    db.refresh(removal)
    assert removal.status == "done"
    assert owner.get(f"/api/access-reviews/{rid}").json()["removals_unverified"] == 0

    done = owner.post(f"/api/access-reviews/{rid}/complete").json()
    assert done["status"] == "completed" and done["evidence_id"]
    ev = db.get(Evidence, done["evidence_id"])
    assert ev.file_name.endswith(".csv") and db.get(Control, ev.control_id).code == "ACC-05"
    csv_text = owner.get(f"/api/evidence/{ev.id}/download").text
    assert "leaver@acme.in" in csv_text and "revoke" in csv_text and "Left in Jan" in csv_text


# ---------------------------------------------------------------- notifications and reminders


def test_notification_queue_dedupes_and_delivers(owner, db, monkeypatch):
    org = db.scalar(select(Organization))
    notify.queue(db, org.id, key="x", event="test", title="Hello", to=["A@acme.in"], broadcast=True)
    notify.queue(db, org.id, key="x", event="test", title="Hello again")
    db.commit()
    assert len(db.scalars(select(Notification).where(Notification.dedupe_key == "x")).all()) == 1

    assert owner.put("/api/org/notifications", json={"slack_webhook_url": "https://evil.example/hook"}).status_code == 400
    r = owner.put("/api/org/notifications", json={"slack_webhook_url": "https://hooks.slack.com/services/T/B/X"})
    assert r.json()["slack_configured"] and "hooks.slack.com" not in json.dumps(r.json())
    posted, emailed = [], []
    monkeypatch.setattr(notify.httpx, "post", lambda url, json, timeout: posted.append((url, json)) or
                        httpx.Response(200, request=httpx.Request("POST", url)))
    monkeypatch.setattr(notify, "send_email", lambda to, subject, text: emailed.append((to, subject)))
    db.expire_all()
    assert notify.deliver_pending(db) >= 1
    assert any("Hello" in p[1]["text"] for p in posted)
    assert any(e[0] == ["a@acme.in"] for e in emailed)
    assert db.scalar(select(Notification).where(Notification.dedupe_key == "x")).status == "sent"


def test_reminders_and_recurring_tasks(owner, db):
    org = db.scalar(select(Organization))
    now = datetime.now(timezone.utc)
    owner.post("/api/incidents", json={"title": "Phish", "detected_at": (now - timedelta(hours=5)).isoformat(),
                                       "certin_reportable": True})
    owner.post("/api/dpdp/requests", json={"request_type": "access", "requester_name": "R",
                                           "requester_email": "r@example.com",
                                           "received_at": (now - timedelta(days=40)).isoformat()})
    ctl = next(c for c in owner.get("/api/controls").json() if c["code"] == "LOG-03")
    owner.patch(f"/api/controls/{ctl['id']}", json={"status": "implemented"})
    owner.post(f"/api/controls/{ctl['id']}/evidence", data={
        "title": "NTP", "kind": "note", "description": "chrony", "valid_until": (date.today() + timedelta(days=5)).isoformat()})

    run_reminders(db, now)
    run_reminders(db, now)  # idempotent
    keys = set(db.scalars(select(Notification.dedupe_key).where(Notification.org_id == org.id)))
    incident = db.scalar(select(Incident))
    rr = db.scalar(select(RightsRequest))
    assert f"inc:{incident.id}:certin:2h" in keys and f"rr:{rr.id}:overdue" in keys
    renew = db.scalars(select(Task).where(Task.source.startswith(f"recurring:{ctl['id']}:"))).all()
    assert len(renew) == 1 and renew[0].title.startswith("Renew evidence: LOG-03")


# ---------------------------------------------------------------- public portal


def test_public_portal_flow(owner, db):
    anon = make_client()
    assert anon.get("/api/public/portal/acme").status_code == 404
    r = owner.put("/api/org/portal", json={"portal_enabled": True, "portal_slug": "acme",
                                           "privacy_contact_name": "Asha Rao",
                                           "privacy_contact_email": "privacy@acme.in"})
    assert r.status_code == 200 and r.json()["public_url"].endswith("/p/acme")
    info = anon.get("/api/public/portal/acme").json()
    assert info["org_name"] == "Acme" and info["contact_email"] == "privacy@acme.in"

    bot = anon.post("/api/public/portal/acme/requests", json={
        "request_type": "erasure", "full_name": "Bot", "email": "bot@x.com", "website": "spam"})
    assert bot.status_code == 429
    sent = anon.post("/api/public/portal/acme/requests", json={
        "request_type": "erasure", "full_name": "Meera", "email": "meera@example.com", "details": "Delete my account"})
    assert sent.status_code == 202
    token = sent.json()["dev_verify_url"].split("token=")[1]
    assert db.scalar(select(RightsRequest)) is None  # nothing created until the email is verified

    ok = anon.post("/api/public/portal/acme/verify", json={"token": token}).json()
    assert ok["status"] == "confirmed" and ok["reference"] == "DPR-1"
    rr = db.scalar(select(RightsRequest))
    assert rr.request_type == "erasure" and rr.channel.startswith("web portal") and rr.requester_email == "meera@example.com"
    assert db.scalar(select(Notification).where(Notification.event == "rights_request")).broadcast
    assert anon.post("/api/public/portal/acme/verify", json={"token": token}).json()["status"] == "already_confirmed"
    assert anon.post("/api/public/portal/acme/verify", json={"token": "nope"}).status_code == 404

    other = make_client()
    signup(other, "o@other.in", "Other")
    onboard(other, frameworks=("dpdp",))
    clash = other.put("/api/org/portal", json={"portal_enabled": True, "portal_slug": "acme",
                                               "privacy_contact_name": "X", "privacy_contact_email": "x@other.in"})
    assert clash.status_code == 409


# ---------------------------------------------------------------- personal data discovery


@pytest.fixture
def pii_table(admin_engine):
    from app.services.pii import _VERHOEFF_D, _VERHOEFF_P

    def aadhaar(base):
        inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
        c = 0
        for i, ch in enumerate(reversed(base)):
            c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(ch)]]
        return base + str(inv[c])

    from sqlalchemy.orm import Session

    db = Session(admin_engine)
    db.execute(text("DROP SCHEMA IF EXISTS crm CASCADE"))
    db.execute(text("CREATE SCHEMA crm"))
    db.execute(text("CREATE TABLE crm.customers (id serial, full_name text, contact text, kyc_doc text, "
                    "notes text, date_of_birth date)"))
    for i in range(20):
        db.execute(text("INSERT INTO crm.customers (full_name, contact, kyc_doc, notes) VALUES (:n, :c, :k, :t)"),
                   {"n": f"Customer {i}", "c": f"98765{i:05d}", "k": aadhaar(f"2345678901{i % 10}"),
                    "t": f"PAN ABCPE{1000 + i}F, email c{i}@example.com"})
    db.execute(text("CREATE TABLE crm.settings (key text, value text)"))
    db.execute(text("INSERT INTO crm.settings VALUES ('theme', 'dark')"))
    db.commit()
    yield
    db.execute(text("DROP SCHEMA crm CASCADE"))
    db.commit()
    db.close()


def test_database_scan_finds_masked_pii(owner, db, pii_table):
    from sqlalchemy.engine import make_url

    from tests.conftest import ADMIN_URL

    url = make_url(ADMIN_URL)
    src = owner.post("/api/discovery/sources", json={
        "name": "Prod CRM", "kind": "postgres",
        "config": {"host": url.query.get("host") or url.host or "localhost", "port": str(url.port or 5432),
                   "database": url.database, "username": url.username or "postgres"},
        "secrets": {"password": url.password or ""}}).json()
    scanned = owner.post(f"/api/discovery/sources/{src['id']}/scan")
    assert scanned.status_code == 200, scanned.text
    groups = {g["container"]: g for g in owner.get("/api/discovery/findings").json()}
    customers = groups["crm.customers"]
    assert customers["sensitive"]
    cats = {(f["field"], f["category"]) for f in customers["fields"]}
    assert {("contact", "phone"), ("kyc_doc", "aadhaar"), ("notes", "pan"), ("notes", "email"),
            ("date_of_birth", "dob"), ("full_name", "name")} <= cats
    raw = json.dumps(customers)
    assert "9876500001" not in raw and "c1@example.com" not in raw  # only masked examples are stored
    assert "crm.settings" not in groups

    asset = owner.post("/api/discovery/to-inventory", json={
        "source_id": src["id"], "container": "crm.customers", "name": "Customer KYC"}).json()
    assert "Aadhaar number" in asset["data_categories"]
    assert db.get(DataAsset, asset["id"]).systems == ["Prod CRM: crm.customers"]


def test_s3_scan_with_stub_session(owner, db):
    from app.models import DataSource
    from app.services.scanner import scan_source

    class Body:
        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data

    class Paginator:
        def paginate(self, **kw):
            return [{"Contents": [{"Key": "exports/users.csv", "Size": 10}, {"Key": "logo.png", "Size": 5},
                                  {"Key": "events.jsonl", "Size": 10}]}]

    class S3:
        def get_paginator(self, name):
            return Paginator()

        def get_object(self, Bucket, Key, Range):
            if Key.endswith(".csv"):
                return {"Body": Body(b"name,mobile,upi\nA,9876543210,a.b@okaxis\nB,9123456780,b@ybl\n")}
            return {"Body": Body(b'{"user": {"email": "x@example.com"}}\n')}

    class Session:
        def client(self, name):
            return S3()

    org = db.scalar(select(Organization))
    src = DataSource(org_id=org.id, name="Exports", kind="s3", config={"bucket": "acme-exports"},
                     secret_encrypted=encrypt_json({}))
    db.add(src)
    db.commit()
    scan_source(db, src, session=Session())
    assert src.stats["objects"] == 2
    groups = {g["container"]: g for g in owner.get("/api/discovery/findings").json()}
    csv_cats = {f["category"] for f in groups["s3://acme-exports/exports/users.csv"]["fields"]}
    assert {"phone", "upi"} <= csv_cats
    assert {f["category"] for f in groups["s3://acme-exports/events.jsonl"]["fields"]} == {"email"}


def test_new_endpoints_are_tenant_isolated(owner, db, monkeypatch):
    owner.post("/api/people/upload", files={"file": ("people.csv", ROSTER.encode(), "text/csv")})
    integ = _connect_fake_google(db, monkeypatch, lambda: gws_users())
    sync_integration(db, integ)
    rid = owner.post("/api/access-reviews", json={"title": "R", "providers": ["google_workspace"]}).json()["id"]
    item = owner.get(f"/api/access-reviews/{rid}").json()["items"][0]
    other = make_client()
    signup(other, "o@other.in", "Other")
    onboard(other, frameworks=("dpdp",))
    assert other.get(f"/api/access-reviews/{rid}").status_code == 404
    assert other.patch(f"/api/access-reviews/{rid}/items/{item['id']}", json={"decision": "keep"}).status_code == 404
    assert other.get("/api/people").json() == [] and other.get("/api/accounts").json() == []
    assert db.scalar(select(Account).where(Account.email == "asha@acme.in")) is not None
