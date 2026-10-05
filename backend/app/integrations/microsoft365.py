import httpx

from app.integrations.base import AccountRecord, CheckResult, Connector, ConnectorError, Field, TestDef

GRAPH = "https://graph.microsoft.com/v1.0"
GLOBAL_ADMIN_TEMPLATE = "62e90394-69f5-4237-9190-012177145e10"


class Microsoft365Connector(Connector):
    provider = "microsoft365"
    name = "Microsoft 365 / Entra ID"
    category = "Identity"
    description = "Checks MFA policy, MFA registration and Global Administrator count. Syncs user accounts."
    setup_help = (
        "In the Entra admin centre, register an app (App registrations > New registration), create a client secret, "
        "and grant these Microsoft Graph application permissions with admin consent: User.Read.All, Policy.Read.All, "
        "RoleManagement.Read.Directory and AuditLog.Read.All. MFA registration details need an Entra ID P1 licence."
    )
    provides_accounts = True
    fields = [
        Field("tenant_id", "Directory (tenant) ID"),
        Field("client_id", "Application (client) ID"),
        Field("client_secret", "Client secret value", secret=True),
        Field("max_admins", "Maximum Global Administrators allowed", required=False, default="4"),
    ]
    tests = [
        TestDef("m365.mfa_policy", "MFA required for all users (Security defaults or Conditional Access)", ["ACC-03"]),
        TestDef("m365.mfa_registered", "All member users registered for MFA", ["ACC-03"]),
        TestDef("m365.global_admins", "Global Administrator count within limit", ["ACC-04"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None
        self._cache: dict = {}

    def _get_token(self) -> str:
        if self._token:
            return self._token
        tenant = (self.config.get("tenant_id") or "").strip()
        r = self.client.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={"grant_type": "client_credentials", "client_id": self.config.get("client_id", "").strip(),
                  "client_secret": self.secrets.get("client_secret", ""),
                  "scope": "https://graph.microsoft.com/.default"},
        )
        if r.status_code != 200:
            detail = (r.json().get("error_description", "") if "json" in r.headers.get("content-type", "") else "")
            raise ConnectorError(f"Microsoft rejected the app credentials. {detail.splitlines()[0] if detail else ''}")
        self._token = r.json()["access_token"]
        return self._token

    def _get_all(self, path: str, params: dict | None = None) -> tuple[list[dict] | None, int]:
        """GET with paging. Returns (items, status). items is None on 403/404."""
        if path in self._cache:
            return self._cache[path], 200
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        url, items = f"{GRAPH}{path}", []
        while url:
            r = self.client.get(url, params=params, headers=headers)
            params = None  # nextLink already contains the query
            if r.status_code in (403, 404):
                return None, r.status_code
            if r.status_code == 401:
                raise ConnectorError("Microsoft Graph rejected the token. Check admin consent was granted.")
            r.raise_for_status()
            body = r.json()
            items.extend(body.get("value", [body] if "value" not in body else []))
            url = body.get("@odata.nextLink")
        self._cache[path] = items
        return items, 200

    def verify(self) -> None:
        for k in ("tenant_id", "client_id"):
            if not self.config.get(k):
                raise ConnectorError(f"{k.replace('_', ' ').title()} is required")
        users, status = self._users()
        if users is None:
            raise ConnectorError("The app can't read users. Grant User.Read.All and admin consent.")

    def _users(self):
        return self._get_all("/users", {"$select": "id,displayName,mail,userPrincipalName,accountEnabled,userType",
                                        "$top": "999"})

    def _global_admin_ids(self) -> set[str] | None:
        members, _ = self._get_all(f"/directoryRoles(roleTemplateId='{GLOBAL_ADMIN_TEMPLATE}')/members")
        return None if members is None else {m["id"] for m in members}

    def _registration(self) -> dict[str, dict] | None:
        rows, _ = self._get_all("/reports/authenticationMethods/userRegistrationDetails")
        return None if rows is None else {r["id"]: r for r in rows}

    def run(self) -> list[CheckResult]:
        out = []
        sd, sd_status = self._get_all("/policies/identitySecurityDefaultsEnforcementPolicy")
        defaults_on = bool(sd and sd[0].get("isEnabled"))
        ca, ca_status = self._get_all("/identity/conditionalAccess/policies")
        ca_mfa = [
            p.get("displayName", "") for p in (ca or [])
            if p.get("state") == "enabled"
            and "All" in ((p.get("conditions") or {}).get("users") or {}).get("includeUsers", [])
            and ("mfa" in ((p.get("grantControls") or {}).get("builtInControls") or [])
                 or (p.get("grantControls") or {}).get("authenticationStrength"))
        ]
        if sd is None and ca is None:
            out.append(CheckResult("m365.mfa_policy", "error", "The app can't read policies. Grant Policy.Read.All."))
        elif defaults_on or ca_mfa:
            how = "Security defaults are on" if defaults_on else f"Conditional Access: {', '.join(ca_mfa)}"
            out.append(CheckResult("m365.mfa_policy", "pass", how))
        else:
            out.append(CheckResult("m365.mfa_policy", "fail",
                                   "Neither Security defaults nor an enabled Conditional Access policy requires MFA "
                                   "for all users"))

        reg = self._registration()
        if reg is None:
            out.append(CheckResult("m365.mfa_registered", "error",
                                   "Can't read MFA registration. Grant AuditLog.Read.All (needs Entra ID P1)."))
        else:
            members = [r for r in reg.values() if r.get("userType", "member") == "member"]
            missing = [r.get("userPrincipalName", "") for r in members if not r.get("isMfaRegistered")]
            out.append(CheckResult("m365.mfa_registered", "fail" if missing else "pass",
                                   f"{len(missing)} of {len(members)} users not registered for MFA" if missing
                                   else f"All {len(members)} users registered for MFA", {"users": missing[:200]}))

        admins = self._global_admin_ids()
        if admins is None:
            out.append(CheckResult("m365.global_admins", "error",
                                   "Can't read directory roles. Grant RoleManagement.Read.Directory."))
        else:
            limit = int(self.config.get("max_admins") or 4)
            out.append(CheckResult("m365.global_admins", "pass" if len(admins) <= limit else "fail",
                                   f"{len(admins)} Global Administrators (limit {limit})"))
        return out

    def list_accounts(self) -> list[AccountRecord]:
        users, _ = self._users()
        admins = self._global_admin_ids() or set()
        reg = self._registration() or {}
        return [
            AccountRecord(
                external_id=u["id"], email=(u.get("mail") or u.get("userPrincipalName") or "").lower(),
                name=u.get("displayName") or "", is_admin=u["id"] in admins,
                is_active=bool(u.get("accountEnabled", True)),
                mfa_enabled=reg[u["id"]].get("isMfaRegistered") if u["id"] in reg else None,
            )
            for u in users or []
        ]
