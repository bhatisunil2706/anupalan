"""Device management popular in India (Scalefusion, Hexnode), Indian HR systems (greytHR, Zoho People),
IT service management (Freshservice) and Bitbucket.

Scalefusion, Hexnode, greytHR and Zoho People are marked beta: their APIs are documented, but some response fields
vary by account configuration, so field mapping is defensive and must be confirmed on a real tenant before general
release.
"""
from datetime import datetime, timedelta, timezone

import httpx

from app.integrations.base import (
    CheckResult,
    Connector,
    ConnectorError,
    Field,
    PersonRecord,
    TestDef,
    guarded_base_url,
)
from app.integrations.devices import STALE_DAYS, _device_results, _ts


def _first(d: dict, *keys):
    for k in keys:
        cur = d
        for part in k.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur not in (None, "", [], {}):
            return cur
    return None


def _bool(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "1", "encrypted", "enabled", "on", "compliant"):
        return True
    if s in ("false", "no", "0", "not encrypted", "disabled", "off", "non-compliant", "noncompliant"):
        return False
    return None


def _major(v) -> int | None:
    head = str(v or "").split(".")[0].strip()
    return int(head) if head.isdigit() else None


def _mdm_results(prefix: str, devices: list[dict]) -> list[CheckResult]:
    results = _device_results(prefix, devices)
    if devices and all(d["encrypted"] is None for d in devices):
        results = [r if r.key != f"{prefix}.encrypted" else CheckResult(
            r.key, "error", "This account doesn't report disk encryption; enable it in the MDM's device profile")
            for r in results]
    return results


# ---------------------------------------------------------------- Scalefusion


class ScalefusionConnector(Connector):
    provider = "scalefusion"
    name = "Scalefusion"
    category = "Devices"
    beta = True
    description = "Checks managed laptops and phones are encrypted, compliant and checking in."
    setup_help = "In the Scalefusion dashboard go to Integrations > API and generate an API key."
    fields = [Field("api_key", "API key", secret=True)]
    tests = [
        TestDef("scalefusion.encrypted", "Managed devices are encrypted", ["AST-05", "CRY-01"]),
        TestDef("scalefusion.compliant", "Managed devices meet compliance policies", ["AST-05", "OPS-04"]),
        TestDef("scalefusion.checkin", f"Devices checked in within {STALE_DAYS} days", ["AST-01"]),
    ]
    BASE = "https://api.scalefusion.com"

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Token {secrets.get('api_key', '')}"}

    def devices(self) -> list[dict]:
        out, page = [], 1
        while page <= 100:
            r = self.client.get(f"{self.BASE}/api/v1/devices.json", params={"page": page}, headers=self.headers)
            if r.status_code in (401, 403):
                raise ConnectorError("Scalefusion rejected the API key.")
            r.raise_for_status()
            body = r.json()
            batch = [x.get("device", x) for x in (body.get("devices") or [])]
            out += batch
            if not batch or not body.get("next_page"):
                break
            page += 1
        return out

    def verify(self) -> None:
        self.devices()

    def run(self) -> list[CheckResult]:
        devices = [{"name": _first(d, "name", "device_name") or str(d.get("id")),
                    "encrypted": _bool(_first(d, "encryption_status", "is_encrypted", "device_encrypted",
                                              "storage_encryption")),
                    "compliant": _bool(_first(d, "compliance_status", "is_compliant")),
                    "last_seen": _ts(_first(d, "last_connected_at", "last_seen_on", "last_sync_at"))}
                   for d in self.devices()]
        return _mdm_results("scalefusion", devices)


# ---------------------------------------------------------------- Hexnode


class HexnodeConnector(Connector):
    provider = "hexnode"
    name = "Hexnode UEM"
    category = "Devices"
    beta = True
    description = "Checks managed laptops and phones are encrypted, compliant and checking in."
    setup_help = ("In Hexnode go to Admin > API, enable API access and copy the key. "
                  "Enter your portal, e.g. acme.hexnodemdm.com.")
    fields = [Field("portal", "Hexnode portal", help="For example acme.hexnodemdm.com"),
              Field("api_key", "API key", secret=True)]
    tests = [
        TestDef("hexnode.encrypted", "Managed devices are encrypted", ["AST-05", "CRY-01"]),
        TestDef("hexnode.compliant", "Managed devices meet compliance policies", ["AST-05", "OPS-04"]),
        TestDef("hexnode.checkin", f"Devices checked in within {STALE_DAYS} days", ["AST-01"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("portal", ""), allowed_suffixes=(".hexnodemdm.com",))
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": secrets.get("api_key", "")}

    def devices(self) -> list[dict]:
        out, url = [], f"{self.base}/api/v1/devices/"
        for _ in range(200):
            r = self.client.get(url, headers=self.headers)
            if r.status_code in (401, 403):
                raise ConnectorError("Hexnode rejected the API key.")
            r.raise_for_status()
            body = r.json()
            out += body.get("results") or []
            url = body.get("next")
            if not url:
                break
            if not url.startswith(self.base + "/"):
                raise ConnectorError("Hexnode returned a link to another host")
        return out

    def verify(self) -> None:
        self.devices()

    def run(self) -> list[CheckResult]:
        devices = [{"name": _first(d, "device_name", "name") or str(d.get("id")),
                    "encrypted": _bool(_first(d, "encryption_status", "is_encrypted", "storage_encrypted",
                                              "device_encryption")),
                    "compliant": _bool(_first(d, "compliant", "compliance_status")),
                    "last_seen": _ts(_first(d, "last_reported", "last_seen", "last_checked_in"))}
                   for d in self.devices()]
        return _mdm_results("hexnode", devices)


# ---------------------------------------------------------------- greytHR


class GreytHRConnector(Connector):
    provider = "greythr"
    name = "greytHR"
    category = "HR"
    beta = True
    description = "Imports employees, joining and exit dates for leaver checks and access reviews."
    setup_help = (
        "Ask greytHR support to enable API access, then create API credentials (client ID and secret) in greytHR "
        "Admin > Settings > API. Enter your greytHR domain, e.g. acme.greythr.com."
    )
    provides_people = True
    fields = [Field("domain", "greytHR domain", help="For example acme.greythr.com"),
              Field("client_id", "API client ID"), Field("client_secret", "API client secret", secret=True)]
    tests = []
    API = "https://api.greythr.com"

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("domain", ""), allowed_suffixes=(".greythr.com",))
        self.domain = self.base.removeprefix("https://")
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None

    def _h(self) -> dict:
        if not self._token:
            r = self.client.post(f"{self.base}/uas/v1/oauth2/client-token",
                                 auth=(self.config.get("client_id", ""), self.secrets.get("client_secret", "")))
            if r.status_code != 200:
                raise ConnectorError("greytHR rejected the API credentials.")
            self._token = r.json().get("access_token")
        return {"ACCESS-TOKEN": self._token, "x-greythr-domain": self.domain}

    def verify(self) -> None:
        self._h()

    def list_people(self) -> list[PersonRecord]:
        from app.services.people import infer_status, parse_date  # avoid an import cycle

        rows, page = [], 1
        while page <= 200:
            r = self.client.get(f"{self.API}/employee/v2/employees", params={"page": page, "size": 100},
                                headers=self._h())
            r.raise_for_status()
            body = r.json()
            batch = body.get("data") or []
            rows += batch
            if not batch or not (body.get("pages") or {}).get("hasNext"):
                break
            page += 1
        out = []
        for e in rows:
            email = str(_first(e, "email", "officialEmail", "workEmail") or "").strip().lower()
            if "@" not in email:
                continue
            exit_date = parse_date(str(_first(e, "leavingDate", "dateOfLeaving", "exitDate") or ""))
            out.append(PersonRecord(
                email=email, full_name=str(_first(e, "name", "employeeName") or ""),
                employee_id=str(_first(e, "employeeNo", "employeeId") or ""),
                status=infer_status(str(_first(e, "status", "employeeStatus") or ""), exit_date),
                join_date=parse_date(str(_first(e, "dateOfJoin", "joiningDate") or "")), exit_date=exit_date))
        return out


# ---------------------------------------------------------------- Zoho People


class ZohoPeopleConnector(Connector):
    provider = "zoho_people"
    name = "Zoho People"
    category = "HR"
    beta = True
    description = "Imports employees, managers, joining and exit dates for leaver checks and access reviews."
    setup_help = (
        "In the Zoho API Console (api-console.zoho.in) create a Self Client, generate a code with scope "
        "ZOHOPEOPLE.forms.READ, and exchange it for a refresh token. Pick your Zoho data centre."
    )
    provides_people = True
    fields = [Field("data_centre", "Zoho data centre", required=False, default="in", help="in, com, eu or com.au"),
              Field("client_id", "Client ID"), Field("client_secret", "Client secret", secret=True),
              Field("refresh_token", "Refresh token", secret=True)]
    tests = []

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        dc = (config.get("data_centre") or "in").strip().lower()
        if dc not in ("in", "com", "eu", "com.au", "jp"):
            raise ConnectorError("Data centre must be in, com, eu, com.au or jp")
        self.accounts, self.api = f"https://accounts.zoho.{dc}", f"https://people.zoho.{dc}"
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None

    def _h(self) -> dict:
        if not self._token:
            r = self.client.post(f"{self.accounts}/oauth/v2/token", data={
                "refresh_token": self.secrets.get("refresh_token", ""), "client_id": self.config.get("client_id", ""),
                "client_secret": self.secrets.get("client_secret", ""), "grant_type": "refresh_token"})
            token = r.json().get("access_token") if r.status_code == 200 else None
            if not token:
                raise ConnectorError("Zoho rejected the client or refresh token.")
            self._token = token
        return {"Authorization": f"Zoho-oauthtoken {self._token}"}

    def verify(self) -> None:
        self._h()

    def list_people(self) -> list[PersonRecord]:
        from app.services.people import infer_status, parse_date  # avoid an import cycle

        records, start = [], 1
        while start < 20000:
            r = self.client.get(f"{self.api}/people/api/forms/employee/getRecords",
                                params={"sIndex": start, "limit": 200}, headers=self._h())
            r.raise_for_status()
            result = ((r.json().get("response") or {}).get("result")) or []
            batch = [rec for item in result for recs in item.values() for rec in recs]
            records += batch
            if len(batch) < 200:
                break
            start += 200
        out = []
        for e in records:
            email = str(_first(e, "EmailID", "Email", "Work_Email") or "").strip().lower()
            if "@" not in email:
                continue
            exit_date = parse_date(str(_first(e, "Dateofexit", "Date_of_exit", "Exit_Date") or ""))
            out.append(PersonRecord(
                email=email, full_name=f"{_first(e, 'FirstName') or ''} {_first(e, 'LastName') or ''}".strip(),
                employee_id=str(_first(e, "EmployeeID", "Employee_ID") or ""),
                department=str(_first(e, "Department") or ""), title=str(_first(e, "Designation") or ""),
                manager_email=str(_first(e, "Reporting_To.MailID", "Reporting_To_Email") or "").lower(),
                status=infer_status(str(_first(e, "Employeestatus", "Employee_Status") or ""), exit_date),
                join_date=parse_date(str(_first(e, "Dateofjoining", "Date_of_joining") or "")), exit_date=exit_date))
        return out


# ---------------------------------------------------------------- Freshservice


class FreshserviceConnector(Connector):
    provider = "freshservice"
    name = "Freshservice"
    category = "IT service management"
    description = "Checks the IT asset inventory is maintained and production changes go through change records."
    setup_help = ("In Freshservice open Profile settings and copy your API key. "
                  "Enter your domain, e.g. acme.freshservice.com.")
    fields = [Field("domain", "Freshservice domain", help="For example acme.freshservice.com"),
              Field("api_key", "API key", secret=True)]
    tests = [
        TestDef("freshservice.assets", "IT asset inventory maintained and updated in the last 90 days", ["AST-01"]),
        TestDef("freshservice.changes", "Changes are recorded through change management", ["SDL-05", "RISK-04"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("domain", ""), allowed_suffixes=(".freshservice.com",)) + "/api/v2"
        self.client = client or httpx.Client(timeout=30)
        self.auth = (secrets.get("api_key", ""), "X")

    def _list(self, path: str, key: str, params: dict | None = None, max_pages: int = 30) -> list[dict]:
        out = []
        for page in range(1, max_pages + 1):
            r = self.client.get(f"{self.base}{path}", params={"per_page": 100, "page": page, **(params or {})},
                                auth=self.auth)
            if r.status_code in (401, 403):
                raise ConnectorError("Freshservice rejected the API key.")
            r.raise_for_status()
            batch = r.json().get(key) or []
            out += batch
            if len(batch) < 100:
                break
        return out

    def verify(self) -> None:
        self._list("/assets", "assets", max_pages=1)

    def run(self) -> list[CheckResult]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        assets = self._list("/assets", "assets")
        recent = [a for a in assets if (_ts(a.get("updated_at")) or cutoff) > cutoff]
        out = [CheckResult("freshservice.assets", "pass" if assets and recent else "fail",
                           f"{len(assets)} assets in inventory, {len(recent)} updated in the last 90 days" if assets
                           else "The asset inventory is empty")]
        changes = self._list("/changes", "changes", {"updated_since": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")})
        out.append(CheckResult("freshservice.changes", "pass" if changes else "fail",
                               f"{len(changes)} change records in the last 90 days" if changes
                               else "No change records in the last 90 days"))
        return out


# ---------------------------------------------------------------- Bitbucket


class BitbucketConnector(Connector):
    provider = "bitbucket"
    name = "Bitbucket Cloud"
    category = "Source code"
    description = "Checks main branches require approved pull requests and block direct pushes."
    setup_help = (
        "Create a workspace access token (Workspace settings > Access tokens) with Repositories: Read, or an "
        "Atlassian API token for an account with read access (enter its email too)."
    )
    fields = [Field("workspace", "Workspace ID"),
              Field("email", "Atlassian email (only for API tokens)", required=False),
              Field("token", "Access token", secret=True)]
    tests = [TestDef("bitbucket.branch_protection", "Main branches require an approval and block direct pushes",
                     ["SDL-02", "SDL-05"])]
    BASE = "https://api.bitbucket.org/2.0"

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.ws = (config.get("workspace") or "").strip()
        if not self.ws.replace("-", "").replace("_", "").isalnum():
            raise ConnectorError("Enter the workspace ID shown in the Bitbucket URL")
        self.client = client or httpx.Client(timeout=30)
        email = (config.get("email") or "").strip()
        self.kw = {"auth": (email, secrets.get("token", ""))} if email else {
            "headers": {"Authorization": f"Bearer {secrets.get('token', '')}"}}

    def _values(self, url: str, limit: int = 1000) -> list[dict]:
        out = []
        while url and len(out) < limit:
            if not url.startswith(self.BASE + "/"):
                raise ConnectorError("Bitbucket returned a link to another host")
            r = self.client.get(url, **self.kw)
            if r.status_code in (401, 403):
                raise ConnectorError("Bitbucket rejected the token.")
            r.raise_for_status()
            body = r.json()
            out += body.get("values") or []
            url = body.get("next")
        return out

    def verify(self) -> None:
        self._values(f"{self.BASE}/repositories/{self.ws}?pagelen=1", limit=1)

    def run(self) -> list[CheckResult]:
        repos = self._values(f"{self.BASE}/repositories/{self.ws}?pagelen=100", limit=300)
        bad = []
        for repo in repos:
            main = ((repo.get("mainbranch") or {}).get("name")) or "main"
            rules = self._values(f"{self.BASE}/repositories/{self.ws}/{repo['slug']}/branch-restrictions?pagelen=100")
            applies = [r for r in rules if r.get("pattern") in (main, "*")
                       or (r.get("branch_match_kind") == "branching_model" and r.get("branch_type") == "production")
                       or (r.get("branch_match_kind") == "branching_model" and r.get("branch_type") == "development")]
            approvals = any(r.get("kind") == "require_approvals_to_merge" and int(r.get("value") or 0) >= 1
                            for r in applies)
            no_push = any(r.get("kind") == "push" for r in applies)
            if not (approvals and no_push):
                bad.append(repo.get("full_name") or repo["slug"])
        return [CheckResult("bitbucket.branch_protection", "fail" if bad else "pass",
                            f"{len(bad)} of {len(repos)} repositories don't protect the main branch" if bad
                            else f"Main branch protected in all {len(repos)} repositories",
                            {"failing_repositories": bad[:200]})]
