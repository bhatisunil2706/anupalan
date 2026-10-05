from datetime import datetime, timedelta, timezone

import httpx

from app.integrations.base import (
    AccountRecord,
    CheckResult,
    Connector,
    ConnectorError,
    Field,
    TestDef,
    guarded_base_url,
    link_next,
)

OKTA_SUFFIXES = (".okta.com", ".oktapreview.com", ".okta-emea.com", ".okta-gov.com")
MAX_FACTOR_LOOKUPS = 1000


def _ts(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


class OktaConnector(Connector):
    provider = "okta"
    name = "Okta"
    category = "Identity"
    description = "Checks MFA policy and enrolment, admin count and dormant accounts. Syncs user accounts."
    setup_help = (
        "In the Okta Admin Console go to Security > API > Tokens and create a token as a Read-only Administrator. "
        "Enter your Okta domain, for example acme.okta.com. For custom domains use the original okta.com domain."
    )
    provides_accounts = True
    fields = [
        Field("domain", "Okta domain", help="For example acme.okta.com"),
        Field("api_token", "API token", secret=True),
        Field("max_admins", "Maximum super/org admins allowed", required=False, default="4"),
        Field("dormant_days", "Flag active users with no sign-in for (days)", required=False, default="90"),
    ]
    tests = [
        TestDef("okta.mfa_policy", "Sign-in policy requires MFA for all apps", ["ACC-03"]),
        TestDef("okta.mfa_enrolled", "All active users enrolled in MFA", ["ACC-03"]),
        TestDef("okta.admin_count", "Okta administrator count within limit", ["ACC-04"]),
        TestDef("okta.dormant_users", "No dormant active accounts", ["ACC-05", "ACC-02"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("domain", ""), allowed_suffixes=OKTA_SUFFIXES)
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"SSWS {secrets.get('api_token', '')}", "Accept": "application/json"}
        self._users: list[dict] | None = None
        self._admins: set[str] | None = None
        self._factors: dict[str, bool] = {}

    def _get(self, path_or_url: str, params: dict | None = None) -> httpx.Response:
        url = path_or_url if path_or_url.startswith("https://") else f"{self.base}{path_or_url}"
        if not url.startswith(self.base + "/"):
            raise ConnectorError("Okta returned a link to another host")
        r = self.client.get(url, params=params, headers=self.headers)
        if r.status_code == 401:
            raise ConnectorError("Okta rejected the API token. Check it hasn't expired or been revoked.")
        return r

    def _all(self, path: str, params: dict | None = None) -> list[dict] | None:
        out, url = [], path
        while url:
            r = self._get(url, params)
            params = None
            if r.status_code in (403, 404):
                return None
            r.raise_for_status()
            out.extend(r.json())
            url = link_next(r)
        return out

    def verify(self) -> None:
        r = self._get("/api/v1/users", {"limit": 1})
        if r.status_code == 403:
            raise ConnectorError("The token can't list users. Create it as a Read-only Administrator.")
        r.raise_for_status()

    def users(self) -> list[dict]:
        if self._users is None:
            self._users = [u for u in (self._all("/api/v1/users", {"limit": 200}) or [])
                           if u.get("status") not in ("DEPROVISIONED",)]
        return self._users

    def admins(self) -> set[str] | None:
        if self._admins is None:
            rows = self._all("/api/v1/iam/assignees/users", {"limit": 200})
            self._admins = None if rows is None else {r.get("id") for r in rows}
        return self._admins

    def has_factor(self, user_id: str) -> bool:
        if user_id not in self._factors:
            r = self._get(f"/api/v1/users/{user_id}/factors")
            self._factors[user_id] = r.status_code == 200 and any(f.get("status") == "ACTIVE" for f in r.json())
        return self._factors[user_id]

    def run(self) -> list[CheckResult]:
        out = []
        # Authentication (access) policies: every enabled rule should require two factors.
        policies = self._all("/api/v1/policies", {"type": "ACCESS_POLICY"})
        if policies is None:
            out.append(CheckResult("okta.mfa_policy", "error", "The token can't read authentication policies."))
        else:
            weak = []
            for p in [p for p in policies if p.get("status") == "ACTIVE"]:
                for rule in self._all(f"/api/v1/policies/{p['id']}/rules") or []:
                    if rule.get("status") != "ACTIVE":
                        continue
                    action = ((rule.get("actions") or {}).get("appSignOn") or {})
                    if action.get("access") == "DENY":
                        continue
                    mode = (action.get("verificationMethod") or {}).get("factorMode")
                    if mode != "2FA":
                        weak.append(f"{p.get('name')} / {rule.get('name')}")
            out.append(CheckResult("okta.mfa_policy", "fail" if weak else "pass",
                                   f"{len(weak)} authentication policy rules allow a single factor" if weak else
                                   f"All active rules in {len(policies)} authentication policies require MFA",
                                   {"rules": weak[:100]}))

        active = [u for u in self.users() if u.get("status") == "ACTIVE"]
        missing = [u["profile"].get("login", "") for u in active[:MAX_FACTOR_LOOKUPS] if not self.has_factor(u["id"])]
        checked = min(len(active), MAX_FACTOR_LOOKUPS)
        out.append(CheckResult("okta.mfa_enrolled", "fail" if missing else "pass",
                               f"{len(missing)} of {checked} active users have no MFA factor" if missing
                               else f"All {checked} active users have an MFA factor", {"users": missing[:200]}))

        admins = self.admins()
        if admins is None:
            out.append(CheckResult("okta.admin_count", "error", "The token can't list administrator assignments."))
        else:
            limit = int(self.config.get("max_admins") or 4)
            out.append(CheckResult("okta.admin_count", "pass" if len(admins) <= limit else "fail",
                                   f"{len(admins)} users hold Okta admin roles (limit {limit})"))

        days = int(self.config.get("dormant_days") or 90)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        dormant = [u["profile"].get("login", "") for u in active
                   if (_ts(u.get("lastLogin")) or _ts(u.get("activated")) or cutoff) < cutoff]
        out.append(CheckResult("okta.dormant_users", "fail" if dormant else "pass",
                               f"{len(dormant)} active users haven't signed in for {days}+ days" if dormant
                               else f"No active users idle for more than {days} days", {"users": dormant[:200]}))
        return out

    def list_accounts(self) -> list[AccountRecord]:
        admins = self.admins() or set()
        return [AccountRecord(
            external_id=u["id"], email=(u["profile"].get("email") or u["profile"].get("login") or "").lower(),
            name=f"{u['profile'].get('firstName', '')} {u['profile'].get('lastName', '')}".strip(),
            is_admin=u["id"] in admins, is_active=u.get("status") in ("ACTIVE", "PASSWORD_EXPIRED", "LOCKED_OUT",
                                                                     "RECOVERY"),
            mfa_enabled=self._factors.get(u["id"]), last_login_at=_ts(u.get("lastLogin")),
        ) for u in self.users()]
