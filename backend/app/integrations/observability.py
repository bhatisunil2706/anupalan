"""Monitoring and edge: Datadog (log retention, alerting) and Cloudflare (TLS and HTTPS on public sites)."""
import httpx

from app.integrations.base import CheckResult, Connector, ConnectorError, Field, TestDef

DATADOG_SITES = ("datadoghq.com", "us3.datadoghq.com", "us5.datadoghq.com", "datadoghq.eu", "ap1.datadoghq.com",
                 "ap2.datadoghq.com")


class DatadogConnector(Connector):
    provider = "datadog"
    name = "Datadog"
    category = "Monitoring"
    description = "Checks logs are kept for 180+ days and alert monitors exist and notify someone."
    setup_help = (
        "In Datadog go to Organization settings > API keys and Application keys. Create an application key "
        "with read scopes (monitors_read, logs_read_config). Pick your Datadog site, e.g. ap1.datadoghq.com."
    )
    fields = [
        Field("site", "Datadog site", required=False, default="datadoghq.com", help=", ".join(DATADOG_SITES)),
        Field("api_key", "API key", secret=True),
        Field("app_key", "Application key", secret=True),
        Field("min_retention_days", "Minimum log retention (days)", required=False, default="180"),
    ]
    tests = [
        TestDef("datadog.log_retention", "Log indexes keep logs for the required period", ["LOG-01"]),
        TestDef("datadog.monitors", "Alert monitors are configured and notify a person or channel",
                ["LOG-02", "OPS-05"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        site = (config.get("site") or "datadoghq.com").strip()
        if site not in DATADOG_SITES:
            raise ConnectorError(f"Choose one of: {', '.join(DATADOG_SITES)}")
        self.base = f"https://api.{site}"
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"DD-API-KEY": secrets.get("api_key", ""), "DD-APPLICATION-KEY": secrets.get("app_key", "")}

    def _get(self, path: str, params: dict | None = None):
        r = self.client.get(f"{self.base}{path}", params=params, headers=self.headers)
        if r.status_code in (401, 403):
            raise ConnectorError("Datadog rejected the keys, or the application key lacks read scopes.")
        r.raise_for_status()
        return r.json()

    def verify(self) -> None:
        self._get("/api/v1/validate")

    def run(self) -> list[CheckResult]:
        need = int(self.config.get("min_retention_days") or 180)
        out = []
        try:
            idx = self._get("/api/v1/logs/config/indexes").get("indexes") or []
            short = [f"{i.get('name')} ({i.get('num_retention_days')}d)" for i in idx
                     if int(i.get("num_retention_days") or 0) < need]
            archives = self._get("/api/v2/logs/config/archives").get("data") or []
            if not idx:
                out.append(CheckResult("datadog.log_retention", "fail", "No log indexes configured"))
            elif short and not archives:
                out.append(CheckResult("datadog.log_retention", "fail",
                                       f"{len(short)} indexes keep logs under {need} days and no log archive is set up",
                                       {"short": short}))
            else:
                how = f"all {len(idx)} indexes keep {need}+ days" if not short else f"{len(archives)} log archive(s)"
                out.append(CheckResult("datadog.log_retention", "pass", f"Logs retained: {how}"))
        except httpx.HTTPStatusError as e:
            out.append(CheckResult("datadog.log_retention", "error",
                                   f"Couldn't read log settings ({e.response.status_code})"))
        monitors = self._get("/api/v1/monitor", {"page_size": 1000})
        notifying = [m for m in monitors if "@" in (m.get("message") or "")]
        out.append(CheckResult("datadog.monitors", "pass" if notifying else "fail",
                               f"{len(notifying)} of {len(monitors)} monitors notify someone" if monitors
                               else "No monitors configured",
                               {"silent": [m.get("name") for m in monitors if m not in notifying][:100]}))
        return out


class CloudflareConnector(Connector):
    provider = "cloudflare"
    name = "Cloudflare"
    category = "Network"
    description = "Checks every site forces HTTPS, uses TLS 1.2 or higher and validates the origin certificate."
    setup_help = ("Create an API token in Cloudflare (My Profile > API Tokens) with Zone > Zone Settings: Read "
                  "for all zones.")
    fields = [Field("api_token", "API token", secret=True)]
    tests = [
        TestDef("cloudflare.tls", "All sites force HTTPS with TLS 1.2+ and strict origin certificates", ["NET-02"]),
    ]
    BASE = "https://api.cloudflare.com/client/v4"

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Bearer {secrets.get('api_token', '')}"}

    def _get(self, path: str, params: dict | None = None):
        r = self.client.get(f"{self.BASE}{path}", params=params, headers=self.headers)
        if r.status_code in (401, 403):
            raise ConnectorError("Cloudflare rejected the token or it lacks Zone Settings: Read.")
        r.raise_for_status()
        return r.json().get("result")

    def verify(self) -> None:
        self._get("/user/tokens/verify")

    def run(self) -> list[CheckResult]:
        zones, page = [], 1
        while page < 50:
            batch = self._get("/zones", {"per_page": 50, "page": page}) or []
            zones += batch
            if len(batch) < 50:
                break
            page += 1
        bad = []
        for z in zones:
            settings = {s["id"]: s.get("value") for s in self._get(f"/zones/{z['id']}/settings") or []}
            issues = []
            if settings.get("always_use_https") != "on":
                issues.append("HTTPS not forced")
            if str(settings.get("min_tls_version", "1.0")) < "1.2":
                issues.append(f"minimum TLS {settings.get('min_tls_version')}")
            if settings.get("ssl") not in ("strict", "full_strict", "origin_pull"):
                issues.append(f"SSL mode '{settings.get('ssl')}'")
            if issues:
                bad.append({"zone": z.get("name"), "issues": issues})
        if not zones:
            return [CheckResult("cloudflare.tls", "fail", "No zones visible to this token")]
        return [CheckResult("cloudflare.tls", "fail" if bad else "pass",
                            f"{len(bad)} of {len(zones)} sites need fixing" if bad
                            else f"All {len(zones)} sites force HTTPS with TLS 1.2+ and strict SSL", {"zones": bad})]
