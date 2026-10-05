import json
from datetime import datetime, timedelta, timezone

import httpx

from app.integrations.base import AccountRecord, CheckResult, Connector, ConnectorError, Field, TestDef

DIRECTORY = "https://admin.googleapis.com/admin/directory/v1"
SCOPES = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]
INACTIVE_DAYS = 90
NEVER = "1970-01-01T00:00:00.000Z"


def _ts(value: str | None) -> datetime | None:
    if not value or value.startswith("1970-01-01"):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GoogleWorkspaceConnector(Connector):
    provider = "google_workspace"
    name = "Google Workspace"
    category = "Identity"
    description = "Checks 2-Step Verification, super admin count and inactive users. Syncs user accounts."
    setup_help = (
        "In Google Cloud, create a service account and a JSON key. In the Admin console go to Security > Access and "
        "data control > API controls > Domain-wide delegation, add the service account's client ID with the scope "
        "https://www.googleapis.com/auth/admin.directory.user.readonly. Then enter a super admin email for the "
        "service account to act as."
    )
    provides_accounts = True
    fields = [
        Field("admin_email", "Super admin email to impersonate", help="Read-only access is used, e.g. admin@acme.in"),
        Field("service_account_json", "Service account JSON key", secret=True, multiline=True),
        Field("max_admins", "Maximum super admins allowed", required=False, default="4"),
    ]
    tests = [
        TestDef("gws.2sv_enforced", "2-Step Verification enforced for all active users", ["ACC-03"]),
        TestDef("gws.2sv_enrolled", "All active users enrolled in 2-Step Verification", ["ACC-03"]),
        TestDef("gws.admin_count", "Super admin count within limit", ["ACC-04"]),
        TestDef("gws.inactive_users", f"No active accounts unused for {INACTIVE_DAYS}+ days", ["ACC-02", "ACC-05"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None, token: str | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=30)
        self._token = token
        self._users: list[dict] | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        try:
            info = json.loads(self.secrets.get("service_account_json") or "")
        except json.JSONDecodeError as e:
            raise ConnectorError("The service account key is not valid JSON. Paste the whole downloaded file.") from e
        try:
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES, subject=(self.config.get("admin_email") or "").strip())
            creds.refresh(Request())
        except Exception as e:
            raise ConnectorError(
                "Google rejected the credentials. Check domain-wide delegation is set up for this service account "
                f"with the directory read-only scope, and that the admin email is a super admin. ({e})") from e
        self._token = creds.token
        return self._token

    def _users_all(self) -> list[dict]:
        if self._users is not None:
            return self._users
        users, page = [], None
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        while True:
            params = {"customer": "my_customer", "maxResults": 500, "projection": "basic"}
            if page:
                params["pageToken"] = page
            r = self.client.get(f"{DIRECTORY}/users", params=params, headers=headers)
            if r.status_code in (401, 403):
                raise ConnectorError(f"Google denied access to the user directory ({r.status_code}). "
                                     "Check the delegated scope and admin email.")
            r.raise_for_status()
            body = r.json()
            users.extend(body.get("users", []))
            page = body.get("nextPageToken")
            if not page:
                break
        self._users = users
        return users

    def verify(self) -> None:
        if not self.config.get("admin_email"):
            raise ConnectorError("Admin email is required")
        self._users_all()

    @staticmethod
    def _active(u: dict) -> bool:
        return not u.get("suspended") and not u.get("archived")

    def run(self) -> list[CheckResult]:
        users = [u for u in self._users_all() if self._active(u)]
        total = len(users)
        out = []

        not_enforced = [u["primaryEmail"] for u in users if not u.get("isEnforcedIn2Sv")]
        out.append(CheckResult("gws.2sv_enforced", "fail" if not_enforced else "pass",
                               f"2SV not enforced for {len(not_enforced)} of {total} users" if not_enforced
                               else f"2SV enforced for all {total} users", {"users": not_enforced[:200]}))

        not_enrolled = [u["primaryEmail"] for u in users if not u.get("isEnrolledIn2Sv")]
        out.append(CheckResult("gws.2sv_enrolled", "fail" if not_enrolled else "pass",
                               f"{len(not_enrolled)} of {total} users have not set up 2SV" if not_enrolled
                               else f"All {total} users have set up 2SV", {"users": not_enrolled[:200]}))

        admins = [u["primaryEmail"] for u in users if u.get("isAdmin")]
        limit = int(self.config.get("max_admins") or 4)
        out.append(CheckResult("gws.admin_count", "pass" if len(admins) <= limit else "fail",
                               f"{len(admins)} super admins (limit {limit})", {"admins": admins}))

        cutoff = datetime.now(timezone.utc) - timedelta(days=INACTIVE_DAYS)
        stale = []
        for u in users:
            last = _ts(u.get("lastLoginTime"))
            created = _ts(u.get("creationTime"))
            if (last and last < cutoff) or (last is None and created and created < cutoff):
                stale.append(u["primaryEmail"])
        out.append(CheckResult("gws.inactive_users", "fail" if stale else "pass",
                               f"{len(stale)} active accounts unused for {INACTIVE_DAYS}+ days" if stale
                               else f"No active accounts unused for {INACTIVE_DAYS}+ days", {"users": stale[:200]}))
        return out

    def list_accounts(self) -> list[AccountRecord]:
        return [
            AccountRecord(
                external_id=u["id"], email=u.get("primaryEmail", "").lower(),
                name=(u.get("name") or {}).get("fullName", ""),
                is_admin=bool(u.get("isAdmin") or u.get("isDelegatedAdmin")), is_active=self._active(u),
                mfa_enabled=bool(u.get("isEnrolledIn2Sv")), last_login_at=_ts(u.get("lastLoginTime")),
            )
            for u in self._users_all()
        ]
