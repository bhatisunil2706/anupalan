"""Connectors against mocked provider APIs, the Jira task sync and the scanner agent API."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.integrations import REGISTRY
from app.integrations.base import ConnectorError
from tests.conftest import make_client

NOW = datetime.now(timezone.utc)
OLD = (NOW - timedelta(days=200)).isoformat().replace("+00:00", "Z")
RECENT = (NOW - timedelta(days=2)).isoformat().replace("+00:00", "Z")


def mock(routes: dict):
    """routes: {(method, path): response-json or callable(request) -> httpx.Response}"""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        r = routes.get((request.method, request.url.path))
        if r is None:
            return httpx.Response(404, json={})
        if callable(r):
            return r(request)
        return httpx.Response(200, json=r)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def by_key(results):
    return {r.key: r for r in results}


def test_registry_lists_new_connectors():
    assert {"okta", "azure", "gcp", "gitlab", "jira", "intune", "jamf", "darwinbox"} <= set(REGISTRY)
    for cls in REGISTRY.values():
        d = cls.describe()
        assert d["name"] and d["setup_help"]
        for t in cls.tests:
            assert t.control_codes


def test_okta_checks_and_accounts():
    users = [
        {"id": "u1", "status": "ACTIVE", "lastLogin": RECENT, "profile": {"login": "a@acme.in", "email": "a@acme.in",
                                                                         "firstName": "A", "lastName": "R"}},
        {"id": "u2", "status": "ACTIVE", "lastLogin": OLD, "profile": {"login": "b@acme.in", "email": "b@acme.in"}},
    ]
    client, _ = mock({
        ("GET", "/api/v1/users"): users,
        ("GET", "/api/v1/iam/assignees/users"): [{"id": "u1"}],
        ("GET", "/api/v1/policies"): [{"id": "p1", "name": "Default", "status": "ACTIVE"}],
        ("GET", "/api/v1/policies/p1/rules"): [
            {"name": "Catch-all", "status": "ACTIVE", "actions": {"appSignOn": {"access": "ALLOW",
                                                                               "verificationMethod": {"factorMode": "1FA"}}}}],
        ("GET", "/api/v1/users/u1/factors"): [{"status": "ACTIVE"}],
        ("GET", "/api/v1/users/u2/factors"): [],
    })
    c = REGISTRY["okta"]({"domain": "acme.okta.com"}, {"api_token": "t"}, client=client)
    r = by_key(c.run())
    assert r["okta.mfa_policy"].status == "fail" and "Default / Catch-all" in r["okta.mfa_policy"].details["rules"]
    assert r["okta.mfa_enrolled"].status == "fail" and r["okta.mfa_enrolled"].details["users"] == ["b@acme.in"]
    assert r["okta.admin_count"].status == "pass"
    assert r["okta.dormant_users"].details["users"] == ["b@acme.in"]
    accounts = {a.email: a for a in c.list_accounts()}
    assert accounts["a@acme.in"].is_admin and accounts["a@acme.in"].mfa_enabled


def test_okta_rejects_foreign_domains_and_links():
    with pytest.raises(ConnectorError):
        REGISTRY["okta"]({"domain": "evil.example.com"}, {"api_token": "t"})

    def users(request):
        return httpx.Response(200, json=[], headers={"link": '<https://evil.example.com/x>; rel="next"'})

    client, _ = mock({("GET", "/api/v1/users"): users})
    c = REGISTRY["okta"]({"domain": "acme.okta.com"}, {"api_token": "t"}, client=client)
    with pytest.raises(ConnectorError, match="another host"):
        c.users()


def test_azure_checks():
    sub = "11111111-1111-1111-1111-111111111111"
    base = f"/subscriptions/{sub}/providers"
    client, _ = mock({
        ("POST", "/22222222-2222-2222-2222-222222222222/oauth2/v2.0/token"): {"access_token": "x"},
        ("GET", f"{base}/Microsoft.Security/pricings"): {"value": [{"name": "VirtualMachines",
                                                                     "properties": {"pricingTier": "Standard"}}]},
        ("GET", f"{base}/Microsoft.Storage/storageAccounts"): {"value": [
            {"name": "good", "properties": {"supportsHttpsTrafficOnly": True, "minimumTlsVersion": "TLS1_2",
                                            "allowBlobPublicAccess": False}},
            {"name": "bad", "properties": {"minimumTlsVersion": "TLS1_0"}}]},
        ("GET", f"{base}/Microsoft.Insights/diagnosticSettings"): {"value": []},
        ("GET", f"{base}/Microsoft.Authorization/roleAssignments"): {"value": [
            {"properties": {"roleDefinitionId": "/x/roleDefinitions/8e3af657-a8ff-443c-a75c-2fe8c4bcb635"}}]},
        ("GET", f"/subscriptions/{sub}/resources"): {"value": [{"location": "centralindia"},
                                                                {"location": "eastus"}]},
    })
    c = REGISTRY["azure"]({"tenant_id": "22222222-2222-2222-2222-222222222222", "subscription_id": sub,
                           "client_id": "c", "require_india_region": "yes"}, {"client_secret": "s"}, client=client)
    r = by_key(c.run())
    assert r["azure.defender"].status == "pass"
    assert r["azure.storage_secure"].status == "fail" and r["azure.storage_secure"].details["accounts"][0][
        "account"] == "bad"
    assert r["azure.activity_log"].status == "fail"
    assert r["azure.owner_count"].status == "pass"
    assert r["azure.india_region"].details["regions"] == ["eastus"]
    with pytest.raises(ConnectorError):
        REGISTRY["azure"]({"tenant_id": "../evil", "subscription_id": sub}, {})


def test_gcp_checks():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    sa = {"type": "service_account", "client_email": "scan@acme-prod.iam.gserviceaccount.com", "private_key": pem,
          "private_key_id": "k1"}
    client, _ = mock({
        ("POST", "/token"): {"access_token": "x"},
        ("POST", "/v1/projects/acme-prod:getIamPolicy"): {
            "bindings": [{"role": "roles/owner", "members": ["user:a@acme.in"]},
                         {"role": "roles/storage.objectViewer", "members": ["allUsers"]}],
            "auditConfigs": [{"service": "allServices", "auditLogConfigs": [{"logType": "DATA_READ"},
                                                                             {"logType": "DATA_WRITE"}]}]},
        ("GET", "/storage/v1/b"): {"items": [{"name": "public-assets"},
                                             {"name": "secure", "iamConfiguration": {
                                                 "publicAccessPrevention": "enforced"}}]},
        ("GET", "/v1/projects/acme-prod/serviceAccounts"): {"accounts": [
            {"name": "projects/acme-prod/serviceAccounts/scan", "email": sa["client_email"]},
            {"name": "projects/acme-prod/serviceAccounts/ci", "email": "ci@acme-prod.iam.gserviceaccount.com"}]},
        ("GET", "/v1/projects/acme-prod/serviceAccounts/scan/keys"): {"keys": [{"name": "k1"}]},
        ("GET", "/v1/projects/acme-prod/serviceAccounts/ci/keys"): {"keys": [{"name": "k2"}]},
    })
    c = REGISTRY["gcp"]({"project_id": "acme-prod"}, {"service_account_json": json.dumps(sa)}, client=client)
    r = by_key(c.run())
    assert r["gcp.owner_count"].status == "pass"
    assert r["gcp.no_public_iam"].status == "fail"
    assert r["gcp.audit_logs"].status == "pass"
    assert r["gcp.bucket_public_access"].details["buckets"] == ["public-assets"]
    assert r["gcp.sa_keys"].details["accounts"] == ["ci@acme-prod.iam.gserviceaccount.com"]


def test_gitlab_checks():
    client, _ = mock({
        ("GET", "/api/v4/groups/acme"): {"id": 1, "require_two_factor_authentication": False},
        ("GET", "/api/v4/groups/acme/projects"): [
            {"id": 10, "path_with_namespace": "acme/api", "default_branch": "main"},
            {"id": 11, "path_with_namespace": "acme/web", "default_branch": "main"}],
        ("GET", "/api/v4/projects/10/protected_branches/main"): {"push_access_levels": [{"access_level": 40}]},
        ("GET", "/api/v4/projects/10/approvals"): {"approvals_before_merge": 1},
        ("GET", "/api/v4/projects/11/approvals"): {"approvals_before_merge": 0},
        ("GET", "/api/v4/projects/11/approval_rules"): [],
        ("GET", "/api/v4/groups/acme/members/all"): [
            {"id": 1, "username": "asha", "access_level": 50, "state": "active", "email": "asha@acme.in"},
            {"id": 2, "username": "dev", "access_level": 30, "state": "active"}],
    })
    c = REGISTRY["gitlab"]({"group": "acme"}, {"token": "t"}, client=client)
    r = by_key(c.run())
    assert r["gitlab.group_2fa"].status == "fail"
    assert r["gitlab.protected_branches"].details["failing_projects"] == ["acme/web"]
    assert r["gitlab.mr_approvals"].details["failing_projects"] == ["acme/web"]
    assert r["gitlab.owner_count"].status == "pass"
    assert [a.is_admin for a in c.list_accounts()] == [True, False]
    with pytest.raises(ConnectorError):
        REGISTRY["gitlab"]({"group": "acme", "base_url": "http://gitlab.internal"}, {"token": "t"})


def test_device_connectors():
    client, _ = mock({
        ("POST", "/t1/oauth2/v2.0/token"): {"access_token": "x"},
        ("GET", "/v1.0/deviceManagement/managedDevices"): {"value": [
            {"deviceName": "LAP-1", "userPrincipalName": "a@acme.in", "complianceState": "compliant",
             "isEncrypted": True, "lastSyncDateTime": RECENT},
            {"deviceName": "LAP-2", "userPrincipalName": "b@acme.in", "complianceState": "noncompliant",
             "isEncrypted": False, "lastSyncDateTime": OLD}]},
    })
    r = by_key(REGISTRY["intune"]({"tenant_id": "t1", "client_id": "c"}, {"client_secret": "s"}, client=client).run())
    assert r["intune.encrypted"].status == "fail" and r["intune.compliant"].status == "fail"
    assert r["intune.checkin"].details["devices"] == ["LAP-2 (b@acme.in)"]

    client, _ = mock({
        ("POST", "/api/oauth/token"): {"access_token": "x"},
        ("GET", "/api/v1/computers-inventory"): {"totalCount": 2, "results": [
            {"id": "1", "general": {"name": "MBP-1", "lastContactTime": RECENT},
             "diskEncryption": {"fileVault2Status": "ALL_ENCRYPTED"}, "operatingSystem": {"version": "15.1"}},
            {"id": "2", "general": {"name": "MBP-2", "lastContactTime": RECENT},
             "diskEncryption": {"fileVault2Status": "NOT_ENCRYPTED"}, "operatingSystem": {"version": "13.6.1"}}]},
    })
    r = by_key(REGISTRY["jamf"]({"url": "https://acme.jamfcloud.com", "client_id": "c"}, {"client_secret": "s"},
                                client=client).run())
    assert r["jamf.encrypted"].details["devices"] == ["MBP-2"]
    assert r["jamf.os_current"].details["devices"] == ["MBP-2"]
    assert r["jamf.checkin"].status == "pass"


def test_darwinbox_people():
    client, _ = mock({("POST", "/masterapi/employee"): {"status": 1, "employee_data": [
        {"company_email_id": "Asha@Acme.in", "full_name": "Asha Rao", "employee_id": "E1", "designation": "CTO",
         "date_of_joining": "2021-04-01", "employee_status": "Active"},
        {"company_email_id": "ravi@acme.in", "first_name": "Ravi", "last_name": "K",
         "date_of_exit": "2025-01-31", "employee_status": "Exited"},
        {"full_name": "No email"}]}})
    people = REGISTRY["darwinbox"]({"domain": "acme.darwinbox.in", "username": "u"}, {"password": "p"},
                                   client=client).list_people()
    assert [(p.email, p.status) for p in people] == [("asha@acme.in", "active"), ("ravi@acme.in", "exited")]
    assert people[1].full_name == "Ravi K"


def test_jira_task_sync(owner, db):
    from app.models import Task

    created = []

    def create_issue(request):
        body = json.loads(request.content)
        created.append(body["fields"])
        return httpx.Response(201, json={"key": f"SEC-{len(created)}"})

    def search(request):
        jql = json.loads(request.content)["jql"]
        assert jql.startswith("key in (")
        return httpx.Response(200, json={"issues": [
            {"key": "SEC-1", "fields": {"status": {"statusCategory": {"key": "done"}}}}]})

    owner.post("/api/tasks", json={"title": "Turn on MFA", "priority": "high"})
    owner.post("/api/tasks", json={"title": "Tidy wiki", "priority": "low"})
    client, _ = mock({("POST", "/rest/api/3/issue"): create_issue, ("POST", "/rest/api/3/search/jql"): search})
    jira = REGISTRY["jira"]({"site": "https://acme.atlassian.net", "email": "a@acme.in", "project_key": "SEC",
                             "min_priority": "high"}, {"api_token": "t"}, client=client)
    from app.models import Organization

    org = db.scalar(select(Organization))
    first = jira.sync_tasks(db, org.id)
    db.commit()
    assert [f["summary"] for f in created] == ["Turn on MFA"]
    t = db.scalar(select(Task).where(Task.title == "Turn on MFA"))
    assert t.external_ref == "SEC-1" and t.external_url == "https://acme.atlassian.net/browse/SEC-1"
    assert first["created"] == 1 and first["closed"] == 1  # closed in Jira on the same run
    db.refresh(t)
    assert t.status == "done"
    with pytest.raises(ConnectorError):
        REGISTRY["jira"]({"site": "https://jira.evil.com", "project_key": "SEC"}, {"api_token": "t"})


def test_scanner_agent_api_remasks_examples(owner):
    key = owner.post("/api/org/api-keys", json={"name": "agent", "scopes": ["scanner:write"]}).json()["secret"]
    agent = make_client()
    report = {"source_name": "orders-db", "source_kind": "postgres", "stats": {"tables": 3},
              "findings": [{"container": "public.customers", "field": "pan", "category": "pan", "matches": 40,
                            "sampled": 50, "examples": ["ABCDE1234F"]},
                           {"container": "public.x", "field": "y", "category": "made_up", "examples": ["z"]}]}
    r = agent.post("/api/v1/scanner/findings", json=report, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200, r.text
    assert r.json()["findings"] == 1
    findings = owner.get("/api/discovery/findings").json()
    ex = findings[0]["fields"][0]["examples"][0]
    assert "ABCDE1234" not in ex and ex.endswith("234F")
    src = next(s for s in owner.get("/api/discovery/sources").json() if s["name"] == "orders-db")
    assert src["kind"] == "agent"
    assert owner.post(f"/api/discovery/sources/{src['id']}/scan").status_code == 400
    # a consent key can't post scanner results
    ck = owner.post("/api/org/api-keys", json={"name": "c", "scopes": ["consent:write"]}).json()["secret"]
    assert agent.post("/api/v1/scanner/findings", json=report,
                      headers={"Authorization": f"Bearer {ck}"}).status_code == 403


def test_connect_reports_unreachable_hosts(owner, monkeypatch):
    from starlette.testclient import TestClient

    real = httpx.Client.request

    def boom(self, *a, **k):
        # newer Starlette routes TestClient calls through httpx.Client.request too; only fail outbound calls
        if isinstance(self, TestClient):
            return real(self, *a, **k)
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx.Client, "request", boom)
    r = owner.post("/api/integrations/gitlab", json={"config": {"group": "acme"}, "secrets": {"token": "t"}})
    assert r.status_code == 400 and "reach" in r.json()["detail"]
