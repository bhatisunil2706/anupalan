"""Vulnerability scanners and endpoint security: Snyk, Tenable Vulnerability Management, CrowdStrike Falcon,
SentinelOne. All read-only."""
from datetime import datetime, timedelta, timezone

import httpx

from app.integrations.base import CheckResult, Connector, ConnectorError, Field, TestDef, guarded_base_url, sla_result

STALE_DAYS = 7
SLA_FIELDS = [
    Field("critical_days", "Days to fix critical vulnerabilities", required=False, default="15"),
    Field("high_days", "Days to fix high vulnerabilities", required=False, default="30"),
]


def _ts(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _checkin_result(key: str, hosts: list[tuple[str, datetime | None]], what: str) -> CheckResult:
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
    stale = [h for h, seen in hosts if not seen or seen < cutoff]
    if not hosts:
        return CheckResult(key, "fail", f"No {what} are reporting")
    return CheckResult(key, "fail" if stale else "pass",
                       f"{len(stale)} of {len(hosts)} {what} haven't reported for {STALE_DAYS}+ days" if stale
                       else f"All {len(hosts)} {what} reported within {STALE_DAYS} days", {"stale": stale[:200]})


# ---------------------------------------------------------------- Snyk


class SnykConnector(Connector):
    provider = "snyk"
    name = "Snyk"
    category = "Vulnerability scanning"
    description = ("Checks your code and dependencies are being scanned and no critical or high issue is past its "
                   "fix deadline.")
    setup_help = (
        "In Snyk go to Settings > Service accounts and create one with the Org Viewer role (or use a personal API "
        "token). Copy the organisation ID from Settings > General. Choose your region's API host if not US."
    )
    fields = [
        Field("org_id", "Organisation ID"),
        Field("token", "API token", secret=True),
        Field("api_host", "API host", required=False, default="api.snyk.io",
              help="api.snyk.io (US), api.eu.snyk.io (EU) or api.au.snyk.io (AU)"),
        *SLA_FIELDS,
    ]
    tests = [
        TestDef("snyk.projects", "Code and dependencies are being scanned by Snyk", ["SDL-03", "OPS-02"]),
        TestDef("snyk.vuln_sla", "No critical or high Snyk issues open past the fix deadline", ["OPS-02", "SDL-03"]),
    ]
    VERSION = "2024-10-15"

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        host = (config.get("api_host") or "api.snyk.io").strip()
        if host not in ("api.snyk.io", "api.eu.snyk.io", "api.au.snyk.io", "api.us.snyk.io"):
            raise ConnectorError("Choose api.snyk.io, api.eu.snyk.io or api.au.snyk.io")
        self.base = f"https://{host}/rest"
        self.org = (config.get("org_id") or "").strip()
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"token {secrets.get('token', '')}", "Accept": "application/vnd.api+json"}

    def _all(self, path: str, params: dict) -> list[dict]:
        out, url, p = [], f"{self.base}{path}", {"version": self.VERSION, "limit": 100, **params}
        for _ in range(50):
            r = self.client.get(url, params=p, headers=self.headers)
            if r.status_code in (401, 403):
                raise ConnectorError("Snyk rejected the token or it can't read this organisation.")
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("data", []))
            nxt = (body.get("links") or {}).get("next")
            if not nxt:
                break
            host = f"https://{self.base.split('/')[2]}"
            url = nxt if nxt.startswith("https://") else host + nxt if nxt.startswith("/rest/") else self.base + nxt
            p = None  # the next link carries its own query
            if not url.startswith(host + "/"):
                raise ConnectorError("Snyk returned a link to another host")
        return out

    def verify(self) -> None:
        if not self.org:
            raise ConnectorError("Organisation ID is required")
        self._all(f"/orgs/{self.org}/projects", {"limit": 1})

    def run(self) -> list[CheckResult]:
        projects = self._all(f"/orgs/{self.org}/projects", {})
        out = [CheckResult("snyk.projects", "pass" if projects else "fail",
                           f"{len(projects)} projects monitored by Snyk" if projects
                           else "No projects are being scanned by Snyk")]
        issues = self._all(f"/orgs/{self.org}/issues", {"status": "open", "effective_severity_level": "critical,high"})
        out.append(sla_result("snyk.vuln_sla", [
            {"severity": (i.get("attributes") or {}).get("effective_severity_level"),
             "created_at": (i.get("attributes") or {}).get("created_at"),
             "name": (i.get("attributes") or {}).get("title", "")} for i in issues], self.config))
        return out


# ---------------------------------------------------------------- Tenable


class TenableConnector(Connector):
    provider = "tenable"
    name = "Tenable Vulnerability Management"
    category = "Vulnerability scanning"
    description = "Checks infrastructure is scanned at least monthly and critical or high findings are fixed on time."
    setup_help = (
        "In Tenable Vulnerability Management (cloud.tenable.com) create API keys for a user with the Basic or "
        "Scan Operator role under Settings > My Account > API Keys."
    )
    fields = [Field("access_key", "Access key", secret=True), Field("secret_key", "Secret key", secret=True),
              *SLA_FIELDS]
    tests = [
        TestDef("tenable.scan_recent", "A vulnerability scan completed in the last 30 days", ["OPS-02"]),
        TestDef("tenable.vuln_sla", "No critical or high vulnerabilities open past the fix deadline", ["OPS-02"]),
    ]
    BASE = "https://cloud.tenable.com"

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=60)
        keys = f"accessKey={secrets.get('access_key', '')};secretKey={secrets.get('secret_key', '')}"
        self.headers = {"X-ApiKeys": keys, "Accept": "application/json"}

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self.client.get(f"{self.BASE}{path}", params=params, headers=self.headers)
        if r.status_code in (401, 403):
            raise ConnectorError("Tenable rejected the API keys.")
        r.raise_for_status()
        return r.json()

    def verify(self) -> None:
        self._get("/scans")

    def run(self) -> list[CheckResult]:
        scans = self._get("/scans").get("scans") or []
        done = [datetime.fromtimestamp(int(s["last_modification_date"]), tz=timezone.utc) for s in scans
                if s.get("status") == "completed" and s.get("last_modification_date")]
        latest = max(done) if done else None
        fresh = latest and latest > datetime.now(timezone.utc) - timedelta(days=30)
        out = [CheckResult("tenable.scan_recent", "pass" if fresh else "fail",
                           f"Last completed scan {latest:%d %b %Y}" if latest else "No completed scans found")]
        vulns = self._get("/workbenches/vulnerabilities", {"filter.0.filter": "severity", "filter.0.quality": "gte",
                                                          "filter.0.value": "High"}).get("vulnerabilities") or []
        findings = []
        for v in vulns:
            sev = {4: "critical", 3: "high"}.get(int(v.get("severity", 0)))
            if sev:
                findings.append({"severity": sev, "created_at": v.get("first_found") or v.get("vpr_score_first_seen"),
                                 "name": f"{v.get('plugin_name', '')} ({v.get('count', 1)} assets)"[:200]})
        out.append(sla_result("tenable.vuln_sla", findings, self.config))
        return out


# ---------------------------------------------------------------- CrowdStrike


class CrowdStrikeConnector(Connector):
    provider = "crowdstrike"
    name = "CrowdStrike Falcon"
    category = "Endpoint security"
    description = "Checks Falcon sensors on laptops and servers are reporting and no high-severity alert is left open."
    setup_help = (
        "In the Falcon console go to Support and resources > API clients and keys, and create a client with read "
        "scope for Hosts and Alerts. Pick the cloud your tenant is in."
    )
    fields = [
        Field("cloud", "Falcon cloud", required=False, default="api.crowdstrike.com",
              help="api.crowdstrike.com (US-1), api.us-2.crowdstrike.com, api.eu-1.crowdstrike.com"),
        Field("client_id", "Client ID"),
        Field("client_secret", "Client secret", secret=True),
    ]
    tests = [
        TestDef("crowdstrike.sensors", f"Endpoint sensors reported within {STALE_DAYS} days", ["OPS-01", "AST-05"]),
        TestDef("crowdstrike.open_alerts", "No high or critical alerts left open for over 7 days",
                ["OPS-01", "LOG-02"]),
    ]
    CLOUDS = ("api.crowdstrike.com", "api.us-2.crowdstrike.com", "api.eu-1.crowdstrike.com",
              "api.laggar.gcw.crowdstrike.com")

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        cloud = (config.get("cloud") or "api.crowdstrike.com").strip()
        if cloud not in self.CLOUDS:
            raise ConnectorError(f"Choose one of: {', '.join(self.CLOUDS)}")
        self.base = f"https://{cloud}"
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None

    def _h(self) -> dict:
        if not self._token:
            r = self.client.post(f"{self.base}/oauth2/token", data={
                "client_id": self.config.get("client_id", ""), "client_secret": self.secrets.get("client_secret", "")})
            if r.status_code not in (200, 201):
                raise ConnectorError("CrowdStrike rejected the API client credentials.")
            self._token = r.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    def verify(self) -> None:
        self._h()

    def run(self) -> list[CheckResult]:
        ids, offset = [], 0
        while len(ids) < 20000:
            r = self.client.get(f"{self.base}/devices/queries/devices/v1", params={"limit": 5000, "offset": offset},
                                headers=self._h())
            if r.status_code == 403:
                raise ConnectorError("The API client needs Hosts: Read scope.")
            r.raise_for_status()
            batch = r.json().get("resources") or []
            ids.extend(batch)
            if len(batch) < 5000:
                break
            offset += 5000
        hosts = []
        for i in range(0, len(ids), 100):
            r = self.client.post(f"{self.base}/devices/entities/devices/v2", json={"ids": ids[i:i + 100]},
                                 headers=self._h())
            r.raise_for_status()
            hosts += [(h.get("hostname") or h.get("device_id"), _ts(h.get("last_seen")))
                      for h in r.json().get("resources") or []]
        out = [_checkin_result("crowdstrike.sensors", hosts, "Falcon sensors")]
        week = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = self.client.get(f"{self.base}/alerts/queries/alerts/v2", headers=self._h(), params={
            "filter": f"status:'new'+severity:>=70+created_timestamp:<'{week}'", "limit": 500})
        if r.status_code == 403:
            out.append(CheckResult("crowdstrike.open_alerts", "error", "The API client needs Alerts: Read scope."))
        else:
            r.raise_for_status()
            n = len(r.json().get("resources") or [])
            out.append(CheckResult("crowdstrike.open_alerts", "fail" if n else "pass",
                                   f"{n} high or critical alerts open for over 7 days" if n
                                   else "No high or critical alert open for over 7 days"))
        return out


# ---------------------------------------------------------------- SentinelOne


class SentinelOneConnector(Connector):
    provider = "sentinelone"
    name = "SentinelOne"
    category = "Endpoint security"
    description = "Checks SentinelOne agents are active and up to date, and no threat is left unresolved."
    setup_help = (
        "In the SentinelOne console create a service user with the Viewer role (Settings > Users > Service users) "
        "and generate an API token. Enter your console URL, e.g. https://acme.sentinelone.net."
    )
    fields = [Field("url", "Console URL", help="For example https://acme.sentinelone.net"),
              Field("api_token", "API token", secret=True)]
    tests = [
        TestDef("sentinelone.agents", f"Agents active and reporting within {STALE_DAYS} days", ["OPS-01", "AST-05"]),
        TestDef("sentinelone.threats", "No unresolved threats", ["OPS-01", "LOG-02"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("url", ""), allowed_suffixes=(".sentinelone.net",)) + "/web/api/v2.1"
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"ApiToken {secrets.get('api_token', '')}"}

    def _all(self, path: str, params: dict) -> list[dict]:
        out, cursor = [], None
        for _ in range(100):
            r = self.client.get(f"{self.base}{path}", params={**params, "limit": 1000,
                                                              **({"cursor": cursor} if cursor else {})},
                                headers=self.headers)
            if r.status_code in (401, 403):
                raise ConnectorError("SentinelOne rejected the API token.")
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("data") or [])
            cursor = (body.get("pagination") or {}).get("nextCursor")
            if not cursor:
                break
        return out

    def verify(self) -> None:
        self._all("/agents", {"countOnly": "false"})

    def run(self) -> list[CheckResult]:
        agents = self._all("/agents", {})
        hosts = [(a.get("computerName"), _ts(a.get("lastActiveDate")) if a.get("isActive", True) else None)
                 for a in agents]
        threats = self._all("/threats", {"resolved": "false"})
        names = [f"{(t.get('agentRealtimeInfo') or {}).get('agentComputerName', '')}: "
                 f"{(t.get('threatInfo') or {}).get('threatName', '')}" for t in threats]
        return [_checkin_result("sentinelone.agents", hosts, "SentinelOne agents"),
                CheckResult("sentinelone.threats", "fail" if threats else "pass",
                            f"{len(threats)} unresolved threats" if threats else "No unresolved threats",
                            {"threats": names[:200]})]
