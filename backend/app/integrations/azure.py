import uuid

import httpx

from app.integrations.base import CheckResult, Connector, ConnectorError, Field, TestDef

ARM = "https://management.azure.com"
OWNER_ROLE = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"
INDIA_REGIONS = {"centralindia", "southindia", "westindia", "jioindiawest", "jioindiacentral"}


class AzureConnector(Connector):
    provider = "azure"
    name = "Microsoft Azure"
    category = "Cloud"
    description = ("Checks Defender for Cloud, storage encryption and public access, activity log export, subscription "
                   "owners and where resources are hosted.")
    setup_help = (
        "Register an app in Entra ID, create a client secret, then on the subscription (Access control (IAM)) assign "
        "the app the built-in Reader and Security Reader roles. Read-only; nothing is changed."
    )
    fields = [
        Field("tenant_id", "Directory (tenant) ID"),
        Field("client_id", "Application (client) ID"),
        Field("client_secret", "Client secret value", secret=True),
        Field("subscription_id", "Subscription ID"),
        Field("max_owners", "Maximum subscription owners allowed", required=False, default="3"),
        Field("require_india_region", "Require all resources to be in India (yes/no)", required=False, default="no"),
    ]
    tests = [
        TestDef("azure.defender", "Microsoft Defender for Cloud enabled (Standard tier)", ["OPS-01", "LOG-02"]),
        TestDef("azure.storage_secure", "Storage accounts enforce HTTPS/TLS 1.2 and block public blob access",
                ["NET-02", "ACC-06", "CRY-01"]),
        TestDef("azure.activity_log", "Subscription activity log exported to a workspace or storage", ["LOG-01"]),
        TestDef("azure.owner_count", "Subscription Owner assignments within limit", ["ACC-04"]),
        TestDef("azure.india_region", "Resources hosted in Indian regions", ["PRV-13", "LOG-01"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None
        for k in ("tenant_id", "subscription_id"):
            try:
                uuid.UUID(str(config.get(k, "")).strip())
            except ValueError as e:
                raise ConnectorError(f"{k.replace('_', ' ').capitalize()} must be a GUID") from e
        self.sub = str(config["subscription_id"]).strip()

    def _get_token(self) -> str:
        if not self._token:
            r = self.client.post(
                f"https://login.microsoftonline.com/{self.config['tenant_id'].strip()}/oauth2/v2.0/token",
                data={"grant_type": "client_credentials", "client_id": self.config.get("client_id", "").strip(),
                      "client_secret": self.secrets.get("client_secret", ""),
                      "scope": "https://management.azure.com/.default"})
            if r.status_code != 200:
                raise ConnectorError("Azure rejected the app credentials. Check the client ID and secret.")
            self._token = r.json()["access_token"]
        return self._token

    def _list(self, path: str, api_version: str) -> list[dict] | None:
        url, params, out = f"{ARM}/subscriptions/{self.sub}{path}", {"api-version": api_version}, []
        while url:
            r = self.client.get(url, params=params, headers={"Authorization": f"Bearer {self._get_token()}"})
            params = None
            if r.status_code in (403, 404):
                return None
            if r.status_code == 401:
                raise ConnectorError("Azure rejected the token.")
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("value", []))
            url = body.get("nextLink")
            if url and not url.startswith(ARM + "/"):
                raise ConnectorError("Azure returned a link to another host")
        return out

    def verify(self) -> None:
        r = self.client.get(f"{ARM}/subscriptions/{self.sub}", params={"api-version": "2022-12-01"},
                            headers={"Authorization": f"Bearer {self._get_token()}"})
        if r.status_code in (403, 404):
            raise ConnectorError("The app can't read this subscription. Assign it the Reader role on it.")
        r.raise_for_status()

    def run(self) -> list[CheckResult]:
        out = []
        pricings = self._list("/providers/Microsoft.Security/pricings", "2024-01-01")
        if pricings is None:
            out.append(CheckResult("azure.defender", "error", "Can't read Defender plans. Assign Security Reader."))
        else:
            on = [p["name"] for p in pricings if (p.get("properties") or {}).get("pricingTier") == "Standard"]
            out.append(CheckResult("azure.defender", "pass" if on else "fail",
                                   f"Defender plans on: {', '.join(sorted(on))}" if on
                                   else "No Microsoft Defender for Cloud plans are enabled", {"plans": on}))

        accounts = self._list("/providers/Microsoft.Storage/storageAccounts", "2023-05-01")
        if accounts is None:
            out.append(CheckResult("azure.storage_secure", "error", "Can't list storage accounts."))
        else:
            bad = []
            for a in accounts:
                p = a.get("properties") or {}
                issues = []
                if not p.get("supportsHttpsTrafficOnly", True):
                    issues.append("HTTP allowed")
                if p.get("minimumTlsVersion", "TLS1_0") not in ("TLS1_2", "TLS1_3"):
                    issues.append("TLS below 1.2")
                if p.get("allowBlobPublicAccess", True):
                    issues.append("public blob access allowed")
                if issues:
                    bad.append({"account": a.get("name"), "issues": issues})
            out.append(CheckResult("azure.storage_secure", "fail" if bad else "pass",
                                   f"{len(bad)} of {len(accounts)} storage accounts need fixing" if bad
                                   else f"All {len(accounts)} storage accounts are locked down", {"accounts": bad}))

        diag = self._list("/providers/Microsoft.Insights/diagnosticSettings", "2021-05-01-preview")
        if diag is None:
            out.append(CheckResult("azure.activity_log", "error", "Can't read activity log diagnostic settings."))
        else:
            out.append(CheckResult("azure.activity_log", "pass" if diag else "fail",
                                   f"Activity log exported via {len(diag)} diagnostic setting(s)" if diag
                                   else "The subscription activity log isn't exported, so it is kept only 90 days"))

        roles = self._list("/providers/Microsoft.Authorization/roleAssignments", "2022-04-01")
        if roles is None:
            out.append(CheckResult("azure.owner_count", "error", "Can't read role assignments."))
        else:
            owners = [r for r in roles if str((r.get("properties") or {}).get("roleDefinitionId", "")).lower()
                      .endswith(OWNER_ROLE)]
            limit = int(self.config.get("max_owners") or 3)
            out.append(CheckResult("azure.owner_count", "pass" if len(owners) <= limit else "fail",
                                   f"{len(owners)} Owner role assignments (limit {limit})"))

        require_india = str(self.config.get("require_india_region", "no")).lower() in ("yes", "true", "1")
        resources = self._list("/resources", "2021-04-01") if require_india else None
        if resources is not None:
            located = [r for r in resources if r.get("location") and r["location"] != "global"]
            outside = sorted({r["location"] for r in located if r["location"] not in INDIA_REGIONS})
            out.append(CheckResult("azure.india_region", "fail" if outside else "pass",
                                   f"Resources found outside India: {', '.join(outside)}" if outside
                                   else f"All {len(located)} regional resources are in Indian regions",
                                   {"regions": outside}))
        return out
