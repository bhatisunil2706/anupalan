import json
import re
import time

import httpx
import jwt

from app.integrations.base import CheckResult, Connector, ConnectorError, Field, TestDef

TOKEN_URL = "https://oauth2.googleapis.com/token"  # nosec B105 - URL, not a secret
SCOPE = "https://www.googleapis.com/auth/cloud-platform.read-only"
PUBLIC_MEMBERS = {"allUsers", "allAuthenticatedUsers"}


class GCPConnector(Connector):
    provider = "gcp"
    name = "Google Cloud"
    category = "Cloud"
    description = ("Checks project owners, public IAM grants, public buckets, user-managed service account keys and "
                   "audit logging.")
    setup_help = (
        "Create a service account in the project, grant it the Viewer, Security Reviewer and Storage Object Viewer "
        "roles (or the narrower roles/iam.securityReviewer + roles/storage.legacyBucketReader), create a JSON key "
        "and paste it here. Read-only; nothing is changed."
    )
    fields = [
        Field("project_id", "Project ID"),
        Field("service_account_json", "Service account key (JSON)", secret=True, multiline=True),
        Field("max_owners", "Maximum project owners allowed", required=False, default="3"),
    ]
    tests = [
        TestDef("gcp.owner_count", "Project owner count within limit", ["ACC-04"]),
        TestDef("gcp.no_public_iam", "No IAM roles granted to allUsers or allAuthenticatedUsers", ["ACC-06"]),
        TestDef("gcp.bucket_public_access", "Cloud Storage buckets enforce public access prevention", ["ACC-06"]),
        TestDef("gcp.sa_keys", "No user-managed service account keys", ["ACC-08"]),
        TestDef("gcp.audit_logs", "Data access audit logs enabled for all services", ["LOG-01"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.project = (config.get("project_id") or "").strip()
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", self.project):
            raise ConnectorError("Enter a valid project ID, for example acme-prod-123")
        try:
            self.sa = json.loads(secrets.get("service_account_json") or "{}")
        except json.JSONDecodeError as e:
            raise ConnectorError("The service account key isn't valid JSON") from e
        if self.sa.get("type") != "service_account" or not self.sa.get("private_key"):
            raise ConnectorError("Paste the full JSON key for a service account")
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None
        self._policy: dict | None = None

    def _get_token(self) -> str:
        if not self._token:
            now = int(time.time())
            assertion = jwt.encode({"iss": self.sa["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": now,
                                    "exp": now + 3600}, self.sa["private_key"], algorithm="RS256",
                                   headers={"kid": self.sa.get("private_key_id", "")})
            r = self.client.post(TOKEN_URL, data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                                  "assertion": assertion})
            if r.status_code != 200:
                raise ConnectorError("Google rejected the service account key. It may have been deleted.")
            self._token = r.json()["access_token"]
        return self._token

    def _req(self, method: str, url: str, **kw) -> httpx.Response:
        r = self.client.request(method, url, headers={"Authorization": f"Bearer {self._get_token()}"}, **kw)
        if r.status_code == 401:
            raise ConnectorError("Google rejected the access token.")
        return r

    def policy(self) -> dict | None:
        if self._policy is None:
            r = self._req("POST", f"https://cloudresourcemanager.googleapis.com/v1/projects/{self.project}"
                                  ":getIamPolicy", json={"options": {"requestedPolicyVersion": 3}})
            if r.status_code in (403, 404):
                return None
            r.raise_for_status()
            self._policy = r.json()
        return self._policy

    def verify(self) -> None:
        if self.policy() is None:
            raise ConnectorError("The service account can't read the project's IAM policy. Grant it Security "
                                 "Reviewer on the project.")

    def run(self) -> list[CheckResult]:
        out = []
        policy = self.policy()
        if policy is None:
            err = "Can't read the project IAM policy."
            return [CheckResult(k, "error", err) for k in ("gcp.owner_count", "gcp.no_public_iam", "gcp.audit_logs")]
        bindings = policy.get("bindings", [])
        owners = sorted({m for b in bindings if b.get("role") == "roles/owner" for m in b.get("members", [])})
        limit = int(self.config.get("max_owners") or 3)
        out.append(CheckResult("gcp.owner_count", "pass" if len(owners) <= limit else "fail",
                               f"{len(owners)} project owners (limit {limit})", {"owners": owners}))
        public = [f"{b['role']} -> {m}" for b in bindings for m in b.get("members", []) if m in PUBLIC_MEMBERS]
        out.append(CheckResult("gcp.no_public_iam", "fail" if public else "pass",
                               f"{len(public)} public IAM grants" if public else "No public IAM grants",
                               {"grants": public}))
        audit = {c.get("service"): {x.get("logType") for x in c.get("auditLogConfigs", [])}
                 for c in policy.get("auditConfigs", [])}
        all_svc = audit.get("allServices", set())
        ok = {"DATA_READ", "DATA_WRITE"} <= all_svc
        out.append(CheckResult("gcp.audit_logs", "pass" if ok else "fail",
                               "Data access audit logs on for all services" if ok
                               else "Data access audit logs aren't enabled for all services"))

        r = self._req("GET", "https://storage.googleapis.com/storage/v1/b", params={"project": self.project})
        if r.status_code in (403, 404):
            out.append(CheckResult("gcp.bucket_public_access", "error", "Can't list Cloud Storage buckets."))
        else:
            r.raise_for_status()
            buckets = r.json().get("items", [])
            open_ = [b["name"] for b in buckets
                     if (b.get("iamConfiguration") or {}).get("publicAccessPrevention") != "enforced"]
            out.append(CheckResult("gcp.bucket_public_access", "fail" if open_ else "pass",
                                   f"{len(open_)} of {len(buckets)} buckets don't enforce public access prevention"
                                   if open_ else f"All {len(buckets)} buckets enforce public access prevention",
                                   {"buckets": open_[:200]}))

        r = self._req("GET", f"https://iam.googleapis.com/v1/projects/{self.project}/serviceAccounts",
                      params={"pageSize": 100})
        if r.status_code in (403, 404):
            out.append(CheckResult("gcp.sa_keys", "error", "Can't list service accounts."))
        else:
            r.raise_for_status()
            with_keys = []
            for sa in r.json().get("accounts", []):
                kr = self._req("GET", f"https://iam.googleapis.com/v1/{sa['name']}/keys",
                               params={"keyTypes": "USER_MANAGED"})
                if kr.status_code == 200 and kr.json().get("keys"):
                    with_keys.append(sa.get("email"))
            # the key used by this connector is expected; flag everything else
            others = [e for e in with_keys if e != self.sa.get("client_email")]
            out.append(CheckResult("gcp.sa_keys", "fail" if others else "pass",
                                   f"{len(others)} service accounts have user-managed keys" if others
                                   else "No user-managed keys besides this connector's", {"accounts": others}))
        return out
