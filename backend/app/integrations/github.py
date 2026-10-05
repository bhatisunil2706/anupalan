import httpx

from app.integrations.base import AccountRecord, CheckResult, Connector, ConnectorError, Field, TestDef

API = "https://api.github.com"


class GitHubConnector(Connector):
    provider = "github"
    name = "GitHub"
    category = "Source code"
    description = "Checks organisation MFA, branch protection, secret scanning, Dependabot alerts and admin count."
    setup_help = (
        "Create a fine-grained personal access token (or GitHub App) owned by an organisation admin with read-only "
        "access to Administration, Metadata, Members and Secret scanning alerts for all repositories."
    )
    fields = [
        Field("organization", "GitHub organisation", help="The org login, e.g. acme-inc"),
        Field("token", "Access token", secret=True),
        Field("max_admins", "Maximum org admins allowed", required=False, default="3"),
    ]
    tests = [
        TestDef("github.org_2fa", "Two-factor authentication required for the GitHub organisation", ["ACC-03"]),
        TestDef("github.branch_protection", "Default branches require pull request review", ["SDL-02", "SDL-05"]),
        TestDef("github.secret_scanning", "Secret scanning enabled on all repositories", ["ACC-08", "SDL-03"]),
        TestDef("github.dependabot_alerts", "Dependabot vulnerability alerts enabled on all repositories",
                ["OPS-02", "SDL-03"]),
        TestDef("github.admin_count", "Organisation admin count within limit", ["ACC-04", "ACC-07"]),
    ]

    max_repos = 200
    provides_accounts = True

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.org = (config.get("organization") or "").strip()
        self.client = client or httpx.Client(base_url=API, timeout=20)
        self.headers = {
            "Authorization": f"Bearer {secrets.get('token', '')}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get(self, path: str, **params) -> httpx.Response:
        r = self.client.get(path, headers=self.headers, params=params or None)
        if r.status_code == 401:
            raise ConnectorError("GitHub rejected the token (401). Check that it is valid and not expired.")
        return r

    def verify(self) -> None:
        if not self.org:
            raise ConnectorError("Organisation is required")
        r = self._get(f"/orgs/{self.org}")
        if r.status_code == 404:
            raise ConnectorError(f"Organisation '{self.org}' not found or token has no access to it.")
        r.raise_for_status()

    def _repos(self) -> list[dict]:
        repos, page = [], 1
        while len(repos) < self.max_repos:
            r = self._get(f"/orgs/{self.org}/repos", per_page=100, page=page, type="all")
            r.raise_for_status()
            batch = r.json()
            repos.extend(x for x in batch if not x.get("archived") and not x.get("disabled"))
            if len(batch) < 100:
                break
            page += 1
        return repos[: self.max_repos]

    def run(self) -> list[CheckResult]:
        self.verify()
        out: list[CheckResult] = []
        org = self._get(f"/orgs/{self.org}").json()

        twofa = org.get("two_factor_requirement_enabled")
        if twofa is None:
            out.append(CheckResult("github.org_2fa", "error",
                                   "Token cannot read the org 2FA setting; it needs org admin read access."))
        else:
            out.append(CheckResult("github.org_2fa", "pass" if twofa else "fail",
                                   "2FA is required for all members" if twofa else "2FA is not required for members"))

        repos = self._repos()
        unprotected, no_secret_scan, no_dependabot = [], [], []
        for repo in repos:
            name = repo["name"]
            branch = repo.get("default_branch") or "main"
            prot = self._get(f"/repos/{self.org}/{name}/branches/{branch}/protection")
            reviews = 0
            if prot.status_code == 200:
                reviews = (prot.json().get("required_pull_request_reviews") or {}).get(
                    "required_approving_review_count", 0
                )
            if reviews < 1:
                unprotected.append(name)
            sa = repo.get("security_and_analysis") or {}
            if (sa.get("secret_scanning") or {}).get("status") != "enabled":
                no_secret_scan.append(name)
            va = self._get(f"/repos/{self.org}/{name}/vulnerability-alerts")
            if va.status_code != 204:
                no_dependabot.append(name)

        def coverage(key: str, failing: list[str], ok_msg: str, bad_msg: str) -> CheckResult:
            return CheckResult(
                key,
                "fail" if failing else "pass",
                bad_msg.format(n=len(failing), total=len(repos)) if failing else ok_msg.format(total=len(repos)),
                {"failing_repositories": failing[:50], "repositories_checked": len(repos)},
            )

        out.append(coverage("github.branch_protection", unprotected,
                            "All {total} repositories require at least one approving review",
                            "{n} of {total} repositories do not require pull request review"))
        out.append(coverage("github.secret_scanning", no_secret_scan,
                            "Secret scanning enabled on all {total} repositories",
                            "Secret scanning off on {n} of {total} repositories"))
        out.append(coverage("github.dependabot_alerts", no_dependabot,
                            "Dependabot alerts enabled on all {total} repositories",
                            "Dependabot alerts off on {n} of {total} repositories"))

        admins_r = self._get(f"/orgs/{self.org}/members", role="admin", per_page=100)
        if admins_r.status_code == 200:
            admins = [a["login"] for a in admins_r.json()]
            limit = int(self.config.get("max_admins") or 3)
            out.append(CheckResult("github.admin_count", "pass" if len(admins) <= limit else "fail",
                                   f"{len(admins)} organisation admins (limit {limit})", {"admins": admins}))
        else:
            out.append(CheckResult("github.admin_count", "error", "Could not list organisation admins"))
        return out

    def _members(self, role: str) -> list[dict]:
        out, page = [], 1
        while True:
            r = self._get(f"/orgs/{self.org}/members", role=role, per_page=100, page=page)
            if r.status_code != 200:
                return out
            batch = r.json()
            out.extend(batch)
            if len(batch) < 100:
                return out
            page += 1

    def list_accounts(self) -> list[AccountRecord]:
        admins = {m["login"] for m in self._members("admin")}
        # GitHub hides member emails; access reviews show the login. Map logins to people by name if needed.
        return [AccountRecord(external_id=str(m["id"]), name=m["login"], is_admin=m["login"] in admins)
                for m in self._members("all")]
