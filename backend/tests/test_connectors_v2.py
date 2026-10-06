"""Security tooling, Indian MDM/HR, IT ops connectors (mocked APIs), the evidence push API and coverage."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from app.integrations import REGISTRY
from app.integrations.base import ConnectorError, sla_result
from tests.conftest import make_client
from tests.test_connectors import by_key, mock

NOW = datetime.now(timezone.utc)


def iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def test_sla_helper():
    r = sla_result("x", [{"severity": "critical", "created_at": iso(20), "name": "a"},
                         {"severity": "high", "created_at": iso(10), "name": "b"},
                         {"severity": "medium", "created_at": iso(400), "name": "c"}], {})
    assert r.status == "fail" and [o["name"] for o in r.details["overdue"]] == ["a"]
    assert sla_result("x", [{"severity": "high", "created_at": iso(10)}], {}).status == "pass"
    assert sla_result("x", [{"severity": "high", "created_at": iso(10)}], {"high_days": "5"}).status == "fail"


def test_snyk():
    client, _ = mock({
        ("GET", "/rest/orgs/o1/projects"): {"data": [{"id": "p1"}, {"id": "p2"}], "links": {}},
        ("GET", "/rest/orgs/o1/issues"): {"data": [
            {"attributes": {"effective_severity_level": "critical", "created_at": iso(40), "title": "RCE in lib"}},
            {"attributes": {"effective_severity_level": "high", "created_at": iso(3), "title": "XSS"}}], "links": {}},
    })
    r = by_key(REGISTRY["snyk"]({"org_id": "o1"}, {"token": "t"}, client=client).run())
    assert r["snyk.projects"].status == "pass"
    assert r["snyk.vuln_sla"].status == "fail" and r["snyk.vuln_sla"].details["overdue"][0]["name"] == "RCE in lib"
    with pytest.raises(ConnectorError):
        REGISTRY["snyk"]({"org_id": "o1", "api_host": "evil.example.com"}, {"token": "t"})


def test_tenable():
    client, _ = mock({
        ("GET", "/scans"): {"scans": [{"status": "completed",
                                       "last_modification_date": int((NOW - timedelta(days=3)).timestamp())}]},
        ("GET", "/workbenches/vulnerabilities"): {"vulnerabilities": [
            {"severity": 4, "plugin_name": "OpenSSL", "count": 3, "first_found": iso(5)}]},
    })
    r = by_key(REGISTRY["tenable"]({}, {"access_key": "a", "secret_key": "s"}, client=client).run())
    assert r["tenable.scan_recent"].status == "pass" and r["tenable.vuln_sla"].status == "pass"


def test_crowdstrike():
    client, seen = mock({
        ("POST", "/oauth2/token"): {"access_token": "x"},
        ("GET", "/devices/queries/devices/v1"): {"resources": ["d1", "d2"]},
        ("POST", "/devices/entities/devices/v2"): {"resources": [
            {"hostname": "LAP-1", "last_seen": iso(1)}, {"hostname": "LAP-2", "last_seen": iso(30)}]},
        ("GET", "/alerts/queries/alerts/v2"): {"resources": []},
    })
    r = by_key(REGISTRY["crowdstrike"]({"client_id": "c"}, {"client_secret": "s"}, client=client).run())
    assert r["crowdstrike.sensors"].details["stale"] == ["LAP-2"]
    assert r["crowdstrike.open_alerts"].status == "pass"
    with pytest.raises(ConnectorError):
        REGISTRY["crowdstrike"]({"cloud": "evil.example.com"}, {})


def test_sentinelone():
    client, _ = mock({
        ("GET", "/web/api/v2.1/agents"): {"data": [{"computerName": "MBP-1", "isActive": True,
                                                     "lastActiveDate": iso(0)}], "pagination": {}},
        ("GET", "/web/api/v2.1/threats"): {"data": [{"agentRealtimeInfo": {"agentComputerName": "MBP-1"},
                                                      "threatInfo": {"threatName": "Trojan"}}], "pagination": {}},
    })
    r = by_key(REGISTRY["sentinelone"]({"url": "https://acme.sentinelone.net"}, {"api_token": "t"},
                                       client=client).run())
    assert r["sentinelone.agents"].status == "pass" and r["sentinelone.threats"].details["threats"] == ["MBP-1: Trojan"]
    with pytest.raises(ConnectorError):
        REGISTRY["sentinelone"]({"url": "https://acme.example.com"}, {"api_token": "t"})


def test_datadog_and_cloudflare():
    client, _ = mock({
        ("GET", "/api/v1/logs/config/indexes"): {"indexes": [{"name": "main", "num_retention_days": 15}]},
        ("GET", "/api/v2/logs/config/archives"): {"data": [{"id": "s3-archive"}]},
        ("GET", "/api/v1/monitor"): [{"name": "CPU", "message": "@slack-ops"}, {"name": "Disk", "message": ""}],
    })
    r = by_key(REGISTRY["datadog"]({"site": "ap1.datadoghq.com"}, {"api_key": "a", "app_key": "b"},
                                   client=client).run())
    assert r["datadog.log_retention"].status == "pass"  # short index but archived
    assert r["datadog.monitors"].status == "pass" and r["datadog.monitors"].details["silent"] == ["Disk"]

    client, _ = mock({
        ("GET", "/client/v4/zones"): {"result": [{"id": "z1", "name": "acme.in"}, {"id": "z2", "name": "old.in"}]},
        ("GET", "/client/v4/zones/z1/settings"): {"result": [{"id": "always_use_https", "value": "on"},
                                                             {"id": "min_tls_version", "value": "1.2"},
                                                             {"id": "ssl", "value": "strict"}]},
        ("GET", "/client/v4/zones/z2/settings"): {"result": [{"id": "always_use_https", "value": "off"},
                                                             {"id": "min_tls_version", "value": "1.0"},
                                                             {"id": "ssl", "value": "flexible"}]},
    })
    r = by_key(REGISTRY["cloudflare"]({}, {"api_token": "t"}, client=client).run())
    assert r["cloudflare.tls"].status == "fail" and r["cloudflare.tls"].details["zones"][0]["zone"] == "old.in"


def test_indian_mdms():
    client, _ = mock({("GET", "/api/v1/devices.json"): {"devices": [
        {"device": {"name": "LAP-1", "encryption_status": "Encrypted", "last_connected_at": iso(1)}},
        {"device": {"name": "LAP-2", "encryption_status": "Not Encrypted", "last_connected_at": iso(40)}}]}})
    r = by_key(REGISTRY["scalefusion"]({}, {"api_key": "k"}, client=client).run())
    assert r["scalefusion.encrypted"].details["devices"] == ["LAP-2"]
    assert r["scalefusion.checkin"].details["devices"] == ["LAP-2"]

    client, _ = mock({("GET", "/api/v1/devices/"): {"results": [
        {"device_name": "MBP-1", "last_reported": iso(2)}], "next": None}})
    r = by_key(REGISTRY["hexnode"]({"portal": "acme.hexnodemdm.com"}, {"api_key": "k"}, client=client).run())
    assert r["hexnode.encrypted"].status == "error"  # account doesn't report encryption: never a false pass


def test_indian_hr():
    client, _ = mock({
        ("POST", "/uas/v1/oauth2/client-token"): {"access_token": "x"},
        ("GET", "/employee/v2/employees"): {"data": [
            {"email": "Asha@Acme.in", "name": "Asha", "employeeNo": "E1", "dateOfJoin": "2023-01-02"},
            {"email": "ravi@acme.in", "name": "Ravi", "leavingDate": "2025-03-31", "status": "Inactive"}],
            "pages": {"hasNext": False}},
    })
    people = REGISTRY["greythr"]({"domain": "acme.greythr.com", "client_id": "c"}, {"client_secret": "s"},
                                 client=client).list_people()
    assert [(p.email, p.status) for p in people] == [("asha@acme.in", "active"), ("ravi@acme.in", "exited")]

    client, _ = mock({
        ("POST", "/oauth/v2/token"): {"access_token": "x"},
        ("GET", "/people/api/forms/employee/getRecords"): {"response": {"result": [
            {"101": [{"EmailID": "neha@acme.in", "FirstName": "Neha", "LastName": "Iyer", "Employeestatus": "Active",
                      "Reporting_To.MailID": "asha@acme.in", "Department": "Engineering"}]}]}},
    })
    people = REGISTRY["zoho_people"]({"client_id": "c"}, {"client_secret": "s", "refresh_token": "r"},
                                     client=client).list_people()
    assert people[0].full_name == "Neha Iyer" and people[0].department == "Engineering"


def test_freshservice_and_bitbucket():
    client, _ = mock({("GET", "/api/v2/assets"): {"assets": [{"updated_at": iso(5)}, {"updated_at": iso(300)}]},
                      ("GET", "/api/v2/changes"): {"changes": []}})
    r = by_key(REGISTRY["freshservice"]({"domain": "acme.freshservice.com"}, {"api_key": "k"}, client=client).run())
    assert r["freshservice.assets"].status == "pass" and r["freshservice.changes"].status == "fail"

    def repos(request):
        return httpx.Response(200, json={"values": [{"slug": "api", "full_name": "acme/api",
                                                     "mainbranch": {"name": "main"}},
                                                    {"slug": "web", "full_name": "acme/web",
                                                     "mainbranch": {"name": "main"}}]})

    client, _ = mock({
        ("GET", "/2.0/repositories/acme"): repos,
        ("GET", "/2.0/repositories/acme/api/branch-restrictions"): {"values": [
            {"kind": "require_approvals_to_merge", "pattern": "main", "value": 1},
            {"kind": "push", "pattern": "main"}]},
        ("GET", "/2.0/repositories/acme/web/branch-restrictions"): {"values": []},
    })
    r = by_key(REGISTRY["bitbucket"]({"workspace": "acme"}, {"token": "t"}, client=client).run())
    assert r["bitbucket.branch_protection"].details["failing_repositories"] == ["acme/web"]


def test_github_vuln_sla():
    from tests.test_integrations import connector, github_transport

    base = github_transport(True, True)

    def handler(request):
        if request.url.path == "/orgs/acme/dependabot/alerts":
            return httpx.Response(200, json=[{"created_at": iso(60), "repository": {"name": "api"},
                                              "security_advisory": {"severity": "critical", "summary": "Bad"}}])
        return base.handle_request(request)

    c = connector()
    c.client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    r = by_key(c.run())
    assert r["github.vuln_sla"].status == "fail" and "api: Bad" in r["github.vuln_sla"].details["overdue"][0]["name"]


def test_aws_new_checks():
    from app.integrations.aws import AWSConnector

    clients = {n: MagicMock(name=n) for n in ("sts", "iam", "cloudtrail", "s3control", "ec2", "rds", "guardduty",
                                               "securityhub", "inspector2", "backup", "logs", "organizations")}
    clients["sts"].get_caller_identity.return_value = {"Account": "123"}
    clients["securityhub"].get_enabled_standards.return_value = {"StandardsSubscriptions": [
        {"StandardsArn": "arn:aws:securityhub:ap-south-1::standards/aws-foundational-security-best-practices/v/1.0.0",
         "StandardsStatus": "READY"}]}
    clients["inspector2"].batch_get_account_status.return_value = {"accounts": [
        {"resourceState": {"ec2": {"status": "ENABLED"}, "ecr": {"status": "DISABLED"}}}]}
    clients["backup"].list_backup_plans.return_value = {"BackupPlansList": [{"BackupPlanName": "daily",
                                                                              "BackupPlanId": "b1"}]}
    clients["backup"].list_backup_selections.return_value = {"BackupSelectionsList": [{"SelectionName": "all"}]}
    logs_pager = MagicMock()
    logs_pager.paginate.return_value = [{"logGroups": [{"logGroupName": "/app", "retentionInDays": 30},
                                                       {"logGroupName": "/audit"}]}]
    clients["logs"].get_paginator.return_value = logs_pager
    users_pager = MagicMock()
    users_pager.paginate.return_value = [{"Users": [{"UserName": "ci"}]}]
    clients["iam"].get_paginator.return_value = users_pager
    clients["iam"].list_access_keys.return_value = {"AccessKeyMetadata": [
        {"Status": "Active", "CreateDate": NOW - timedelta(days=200)}]}
    org_pager = MagicMock()
    org_pager.paginate.return_value = [{"Accounts": [{"Name": "prod", "Status": "ACTIVE"},
                                                     {"Name": "dev", "Status": "ACTIVE"}]}]
    clients["organizations"].get_paginator.return_value = org_pager
    session = MagicMock()
    session.client.side_effect = lambda n, **_: clients[n]
    r = by_key(AWSConnector({"region": "ap-south-1"}, {}, session=session).run())
    assert r["aws.security_hub"].status == "pass" and r["aws.inspector"].details["enabled"] == ["ec2"]
    assert r["aws.backup_plans"].status == "pass"
    assert r["aws.log_retention"].details["short"] == ["/app (30d)"]
    assert r["aws.access_key_age"].details["users"] == ["ci"]
    assert r["aws.env_separation"].status == "pass"


def test_registry_has_25_connectors_with_valid_controls():
    import yaml

    codes = {c["code"] for c in yaml.safe_load(open("app/content/controls.yaml"))["controls"]}
    assert len(REGISTRY) >= 25
    for cls in REGISTRY.values():
        for t in cls.tests:
            assert set(t.control_codes) <= codes, (cls.provider, t.key)


# ================================================================ evidence API + coverage


def test_evidence_push_api(owner):
    key = owner.post("/api/org/api-keys", json={"name": "ci", "scopes": ["evidence:write"]}).json()["secret"]
    ci = make_client()
    h = {"Authorization": f"Bearer {key}"}
    ok = ci.post("/api/v1/evidence", headers=h, json={
        "check": "backup-restore", "title": "Nightly restore test", "control_codes": ["OPS-06"], "status": "pass",
        "summary": "Restored 42 GB in 18 minutes", "source": "Jenkins"})
    assert ok.status_code == 201, ok.text
    ctl = next(c for c in owner.get("/api/controls").json() if c["code"] == "OPS-06")
    ev = owner.get(f"/api/controls/{ctl['id']}").json()["evidence"]
    assert any(e["kind"] == "automated" and "Jenkins" in e["title"] for e in ev)
    bad = ci.post("/api/v1/evidence", headers=h, json={"check": "x-y", "title": "abc", "control_codes": ["NOPE-1"],
                                                      "status": "pass"})
    assert bad.status_code == 422
    fail = ci.post("/api/v1/evidence", headers=h, json={"check": "backup-restore", "title": "Nightly restore test",
                                                       "control_codes": ["OPS-06"], "status": "fail"})
    assert fail.status_code == 201
    assert any(t["source"] == "test:api.backup-restore" for t in owner.get("/api/tasks").json())
    assert ci.post("/api/v1/evidence", json={}).status_code == 401


def test_coverage_report(owner):
    cov = owner.get("/api/automation/coverage").json()
    assert cov["total"] > 50 and cov["counts"]["automated"] == 0
    assert cov["percent_hands_off"] > 30  # policies and workflows
    names = [r["provider"] for r in cov["recommendations"]]
    assert "aws" in names[:5]
    key = owner.post("/api/org/api-keys", json={"name": "ci", "scopes": ["evidence:write"]}).json()["secret"]
    make_client().post("/api/v1/evidence", headers={"Authorization": f"Bearer {key}"}, json={
        "check": "restore", "title": "Restore test", "control_codes": ["OPS-06"], "status": "pass"})
    cov = owner.get("/api/automation/coverage").json()
    row = next(r for r in cov["controls"] if r["code"] == "OPS-06")
    assert row["level"] == "automated" and row["integrations"] == ["api"]
