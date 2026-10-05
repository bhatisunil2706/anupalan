from urllib.parse import quote

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

OWNER = 50
MAINTAINER = 40


class GitLabConnector(Connector):
    provider = "gitlab"
    name = "GitLab"
    category = "Source code"
    description = "Checks group 2FA, protected default branches with approvals, and owner count. Syncs members."
    setup_help = (
        "Create a group access token (or a personal token of a group owner) with the read_api scope. For GitLab "
        "self-managed, enter your instance URL; it must be reachable over HTTPS from the internet."
    )
    provides_accounts = True
    fields = [
        Field("base_url", "GitLab URL", required=False, default="https://gitlab.com"),
        Field("group", "Group path", help="For example acme or acme/platform"),
        Field("token", "Access token", secret=True),
        Field("max_owners", "Maximum group owners allowed", required=False, default="3"),
    ]
    tests = [
        TestDef("gitlab.group_2fa", "Two-factor authentication required for the group", ["ACC-03"]),
        TestDef("gitlab.protected_branches", "Default branches protected; no direct pushes by developers",
                ["SDL-02", "SDL-05"]),
        TestDef("gitlab.mr_approvals", "Merge requests need at least one approval", ["SDL-02"]),
        TestDef("gitlab.owner_count", "Group owner count within limit", ["ACC-04", "ACC-07"]),
    ]
    max_projects = 200

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("base_url", ""), default="https://gitlab.com") + "/api/v4"
        self.group = quote((config.get("group") or "").strip().strip("/"), safe="")
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"PRIVATE-TOKEN": secrets.get("token", "")}
        self._members: list[dict] | None = None

    def _get(self, path_or_url: str, params: dict | None = None) -> httpx.Response:
        url = path_or_url if path_or_url.startswith("https://") else f"{self.base}{path_or_url}"
        if not url.startswith(self.base + "/"):
            raise ConnectorError("GitLab returned a link to another host")
        r = self.client.get(url, params=params, headers=self.headers)
        if r.status_code == 401:
            raise ConnectorError("GitLab rejected the token. Check it has read_api and hasn't expired.")
        return r

    def _all(self, path: str, params: dict | None = None, limit: int = 2000) -> list[dict]:
        out, url, params = [], path, {"per_page": 100, **(params or {})}
        while url and len(out) < limit:
            r = self._get(url, params)
            params = None
            r.raise_for_status()
            out.extend(r.json())
            url = link_next(r)
        return out[:limit]

    def verify(self) -> None:
        if not self.group:
            raise ConnectorError("Group path is required")
        r = self._get(f"/groups/{self.group}")
        if r.status_code == 404:
            raise ConnectorError("Group not found, or the token can't see it.")
        r.raise_for_status()

    def members(self) -> list[dict]:
        if self._members is None:
            self._members = self._all(f"/groups/{self.group}/members/all")
        return self._members

    def run(self) -> list[CheckResult]:
        self.verify()
        out = []
        group = self._get(f"/groups/{self.group}").json()
        tfa = group.get("require_two_factor_authentication")
        out.append(CheckResult("gitlab.group_2fa", "pass" if tfa else "fail",
                               "Group requires 2FA" if tfa else "The group doesn't require two-factor authentication"))

        projects = self._all(f"/groups/{self.group}/projects",
                             {"include_subgroups": "true", "archived": "false", "with_shared": "false"},
                             limit=self.max_projects)
        unprotected, no_approvals = [], []
        for p in projects:
            branch = p.get("default_branch")
            if not branch:
                continue
            r = self._get(f"/projects/{p['id']}/protected_branches/{quote(branch, safe='')}")
            if r.status_code == 404:
                unprotected.append(p["path_with_namespace"])
            elif r.status_code == 200:
                levels = [x.get("access_level") for x in r.json().get("push_access_levels", [])]
                if any(lvl is not None and 0 < lvl < MAINTAINER for lvl in levels):
                    unprotected.append(p["path_with_namespace"])
            a = self._get(f"/projects/{p['id']}/approvals")
            if a.status_code == 200 and int(a.json().get("approvals_before_merge") or 0) < 1:
                rules = self._get(f"/projects/{p['id']}/approval_rules")
                if not (rules.status_code == 200 and any(int(x.get("approvals_required") or 0) >= 1
                                                         for x in rules.json())):
                    no_approvals.append(p["path_with_namespace"])
        out.append(CheckResult("gitlab.protected_branches", "fail" if unprotected else "pass",
                               f"{len(unprotected)} of {len(projects)} projects allow direct pushes to the default "
                               "branch" if unprotected
                               else f"Default branches protected in all {len(projects)} projects",
                               {"failing_projects": unprotected[:200]}))
        out.append(CheckResult("gitlab.mr_approvals", "fail" if no_approvals else "pass",
                               f"{len(no_approvals)} projects merge without approval" if no_approvals
                               else "Every project needs an approval to merge",
                               {"failing_projects": no_approvals[:200]}))

        owners = [m["username"] for m in self.members()
                  if m.get("access_level") == OWNER and m.get("state") == "active"]
        limit = int(self.config.get("max_owners") or 3)
        out.append(CheckResult("gitlab.owner_count", "pass" if len(owners) <= limit else "fail",
                               f"{len(owners)} group owners (limit {limit})", {"owners": owners}))
        return out

    def list_accounts(self) -> list[AccountRecord]:
        return [AccountRecord(external_id=str(m["id"]), email=(m.get("email") or m.get("public_email") or "").lower(),
                              name=m.get("name") or m.get("username", ""),
                              is_admin=m.get("access_level", 0) >= OWNER, is_active=m.get("state") == "active")
                for m in self.members()]
