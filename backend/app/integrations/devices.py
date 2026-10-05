"""Device management: Microsoft Intune and Jamf Pro."""
from datetime import datetime, timedelta, timezone

import httpx

from app.integrations.base import CheckResult, Connector, ConnectorError, Field, TestDef, guarded_base_url

STALE_DAYS = 30


def _ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _device_results(prefix: str, devices: list[dict], min_os: int | None = None) -> list[CheckResult]:
    """devices: [{name, user, encrypted, compliant, last_seen, os_major}]"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)
    n = len(devices)
    out = []
    unenc = [d["name"] for d in devices if d["encrypted"] is False]
    out.append(CheckResult(f"{prefix}.encrypted", "fail" if unenc else "pass",
                           f"{len(unenc)} of {n} devices aren't encrypted" if unenc else f"All {n} devices encrypted",
                           {"devices": unenc[:200]}))
    if any(d.get("compliant") is not None for d in devices):
        noncomp = [d["name"] for d in devices if d.get("compliant") is False]
        out.append(CheckResult(f"{prefix}.compliant", "fail" if noncomp else "pass",
                               f"{len(noncomp)} of {n} devices are non-compliant" if noncomp
                               else f"All {n} devices meet compliance policies", {"devices": noncomp[:200]}))
    stale = [d["name"] for d in devices if d["last_seen"] and d["last_seen"] < cutoff]
    out.append(CheckResult(f"{prefix}.checkin", "fail" if stale else "pass",
                           f"{len(stale)} devices haven't checked in for {STALE_DAYS}+ days" if stale
                           else f"All {n} devices checked in within {STALE_DAYS} days", {"devices": stale[:200]}))
    if min_os is not None:
        old = [d["name"] for d in devices if d.get("os_major") is not None and d["os_major"] < min_os]
        out.append(CheckResult(f"{prefix}.os_current", "fail" if old else "pass",
                               f"{len(old)} devices run an OS older than version {min_os}" if old
                               else f"All devices run OS version {min_os} or later", {"devices": old[:200]}))
    return out


class IntuneConnector(Connector):
    provider = "intune"
    name = "Microsoft Intune"
    category = "Devices"
    description = "Checks managed devices are encrypted, compliant and checking in."
    setup_help = (
        "Register an app in Entra ID, create a client secret and grant the Microsoft Graph application permission "
        "DeviceManagementManagedDevices.Read.All with admin consent. You can reuse the Microsoft 365 app."
    )
    fields = [
        Field("tenant_id", "Directory (tenant) ID"),
        Field("client_id", "Application (client) ID"),
        Field("client_secret", "Client secret value", secret=True),
    ]
    tests = [
        TestDef("intune.encrypted", "Managed devices are encrypted", ["AST-05", "CRY-01"]),
        TestDef("intune.compliant", "Managed devices meet compliance policies", ["AST-05", "OPS-04"]),
        TestDef("intune.checkin", f"Devices checked in within {STALE_DAYS} days", ["AST-01"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None

    def _get_token(self) -> str:
        if not self._token:
            r = self.client.post(
                f"https://login.microsoftonline.com/{self.config.get('tenant_id', '').strip()}/oauth2/v2.0/token",
                data={"grant_type": "client_credentials", "client_id": self.config.get("client_id", "").strip(),
                      "client_secret": self.secrets.get("client_secret", ""),
                      "scope": "https://graph.microsoft.com/.default"})
            if r.status_code != 200:
                raise ConnectorError("Microsoft rejected the app credentials.")
            self._token = r.json()["access_token"]
        return self._token

    def devices(self) -> list[dict]:
        url = "https://graph.microsoft.com/v1.0/deviceManagement/managedDevices"
        params = {"$select": "deviceName,userPrincipalName,complianceState,isEncrypted,lastSyncDateTime,"
                             "operatingSystem", "$top": "999"}
        out = []
        while url:
            r = self.client.get(url, params=params, headers={"Authorization": f"Bearer {self._get_token()}"})
            params = None
            if r.status_code == 403:
                raise ConnectorError("Grant DeviceManagementManagedDevices.Read.All with admin consent.")
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("value", []))
            url = body.get("@odata.nextLink")
            if url and not url.startswith("https://graph.microsoft.com/"):
                raise ConnectorError("Microsoft returned a link to another host")
        return out

    def verify(self) -> None:
        self.devices()

    def run(self) -> list[CheckResult]:
        devices = [{"name": f"{d.get('deviceName')} ({d.get('userPrincipalName') or 'no user'})",
                    "encrypted": d.get("isEncrypted"),
                    "compliant": None if d.get("complianceState") in (None, "unknown") else
                    d.get("complianceState") in ("compliant", "inGracePeriod"),
                    "last_seen": _ts(d.get("lastSyncDateTime"))} for d in self.devices()]
        return _device_results("intune", devices)


class JamfConnector(Connector):
    provider = "jamf"
    name = "Jamf Pro"
    category = "Devices"
    description = "Checks Macs have FileVault on, a current macOS version and recent check-ins."
    setup_help = (
        "In Jamf Pro go to Settings > API roles and clients. Create a role with Read Computers and an API client "
        "using it, then generate a client secret. Enter your Jamf Pro URL, e.g. https://acme.jamfcloud.com."
    )
    fields = [
        Field("url", "Jamf Pro URL", help="For example https://acme.jamfcloud.com"),
        Field("client_id", "Client ID"),
        Field("client_secret", "Client secret", secret=True),
        Field("min_macos", "Minimum macOS major version", required=False, default="14"),
    ]
    tests = [
        TestDef("jamf.encrypted", "FileVault enabled on all Macs", ["AST-05", "CRY-01"]),
        TestDef("jamf.checkin", f"Macs checked in within {STALE_DAYS} days", ["AST-01"]),
        TestDef("jamf.os_current", "Macs run a supported macOS version", ["OPS-02", "AST-05"]),
    ]

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("url", ""))
        self.client = client or httpx.Client(timeout=30)
        self._token: str | None = None

    def _get_token(self) -> str:
        if not self._token:
            r = self.client.post(f"{self.base}/api/oauth/token", data={
                "grant_type": "client_credentials", "client_id": self.config.get("client_id", "").strip(),
                "client_secret": self.secrets.get("client_secret", "")})
            if r.status_code != 200:
                raise ConnectorError("Jamf rejected the API client credentials.")
            self._token = r.json()["access_token"]
        return self._token

    def computers(self) -> list[dict]:
        out, page = [], 0
        while page < 50:
            r = self.client.get(f"{self.base}/api/v1/computers-inventory", headers={
                "Authorization": f"Bearer {self._get_token()}"}, params=[
                ("section", "GENERAL"), ("section", "DISK_ENCRYPTION"), ("section", "OPERATING_SYSTEM"),
                ("page", str(page)), ("page-size", "100")])
            if r.status_code in (401, 403):
                raise ConnectorError("The Jamf API client needs the Read Computers privilege.")
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("results", []))
            if len(out) >= int(body.get("totalCount", 0)) or not body.get("results"):
                break
            page += 1
        return out

    def verify(self) -> None:
        self._get_token()

    def run(self) -> list[CheckResult]:
        devices = []
        for c in self.computers():
            general = c.get("general") or {}
            enc = (c.get("diskEncryption") or {}).get("fileVault2Status")
            version = str((c.get("operatingSystem") or {}).get("version") or "")
            devices.append({"name": general.get("name") or c.get("id"),
                            "encrypted": None if enc is None else enc in ("ALL_ENCRYPTED", "BOOT_ENCRYPTED"),
                            "last_seen": _ts(general.get("lastContactTime")),
                            "os_major": int(version.split(".")[0]) if version.split(".")[0].isdigit() else None})
        return _device_results("jamf", devices, min_os=int(self.config.get("min_macos") or 14))
