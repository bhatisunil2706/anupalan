"""Keka HR (beta). Built from Keka's public API docs (developers.keka.com).

The employee response schema is not fully documented publicly, so field mapping is defensive and must be checked
against a Keka sandbox (login.kekademo.com) before general release.
"""
import time

import httpx

from app.integrations.base import Connector, ConnectorError, Field, PersonRecord


def _first(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _text(v) -> str:
    if isinstance(v, dict):
        return str(_first(v, "title", "name", "displayName") or "")
    return str(v or "")


class KekaConnector(Connector):
    provider = "keka"
    name = "Keka HR"
    category = "HR"
    beta = True
    description = "Imports employees, managers, joining and exit dates for leaver checks and access reviews."
    setup_help = (
        "In Keka, go to Settings > Integrations & Automation > API access (or the Keka developer portal) and create "
        "API credentials. You need the client ID, client secret and API key, and your Keka domain, e.g. acme.keka.com."
    )
    provides_people = True
    fields = [
        Field("domain", "Keka domain", help="For example acme.keka.com (sandbox: acme.kekademo.com)"),
        Field("client_id", "Client ID"),
        Field("client_secret", "Client secret", secret=True),
        Field("api_key", "API key", secret=True),
    ]
    tests = []

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.client = client or httpx.Client(timeout=30)
        self.domain = (config.get("domain") or "").strip().removeprefix("https://").strip("/")
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        login = "https://login.kekademo.com" if self.domain.endswith("kekademo.com") else "https://login.keka.com"
        r = self.client.post(f"{login}/connect/token", data={
            "grant_type": "kekaapi", "scope": "kekaapi", "client_id": self.config.get("client_id", "").strip(),
            "client_secret": self.secrets.get("client_secret", ""), "api_key": self.secrets.get("api_key", ""),
        })
        if r.status_code != 200:
            raise ConnectorError("Keka rejected the API credentials. Check the client ID, secret and API key.")
        self._token = r.json()["access_token"]
        return self._token

    def _get(self, path: str, params: dict) -> dict | list:
        for _ in range(4):
            r = self.client.get(f"https://{self.domain}/api/v1{path}", params=params,
                                headers={"Authorization": f"Bearer {self._get_token()}", "Accept": "application/json"})
            if r.status_code == 429:  # Keka allows 50 requests per minute
                time.sleep(min(int(r.headers.get("Retry-After", "5")), 30))
                continue
            if r.status_code in (401, 403):
                raise ConnectorError(f"Keka denied access to employee data ({r.status_code}).")
            r.raise_for_status()
            return r.json()
        raise ConnectorError("Keka rate limit reached. Try again in a minute.")

    def verify(self) -> None:
        if not self.domain or "." not in self.domain:
            raise ConnectorError("Enter your Keka domain, e.g. acme.keka.com")
        self._get("/hris/employees", {"pageNumber": 1, "pageSize": 1})

    def _employees(self, extra: dict) -> list[dict]:
        out, page = [], 1
        while page <= 200:
            body = self._get("/hris/employees", {"pageNumber": page, "pageSize": 200, **extra})
            rows = body.get("data", []) if isinstance(body, dict) else body
            out.extend(rows or [])
            total_pages = body.get("totalPages") if isinstance(body, dict) else None
            if not rows or (total_pages and page >= total_pages) or (total_pages is None and len(rows) < 200):
                break
            page += 1
        return out

    @staticmethod
    def to_person(e: dict) -> PersonRecord | None:
        from app.services.people import infer_status, parse_date  # avoid an import cycle

        email = str(_first(e, "email", "workEmail", "officialEmail", "emailAddress") or "").strip().lower()
        if not email:
            return None
        name = _first(e, "displayName", "fullName") or " ".join(
            x for x in (e.get("firstName"), e.get("lastName")) if x)
        manager = _first(e, "reportsTo", "reportingManager", "reportingTo") or {}
        exit_date = parse_date(str(_first(e, "exitDate", "lastWorkingDate", "lastWorkingDay", "relievingDate") or ""))
        raw_status = _first(e, "employmentStatus", "status")
        status_text = "relieved" if raw_status in (1, "1") else str(raw_status or "")
        return PersonRecord(
            email=email, full_name=str(name or ""), employee_id=str(_first(e, "employeeNumber", "employeeCode") or ""),
            department=_text(_first(e, "department", "departmentName")),
            title=_text(_first(e, "jobTitle", "designation")),
            manager_email=str(manager.get("email", "") if isinstance(manager, dict) else "").lower(),
            status=infer_status(status_text, exit_date),
            join_date=parse_date(str(_first(e, "joiningDate", "dateOfJoining") or "")), exit_date=exit_date,
        )

    def list_people(self) -> list[PersonRecord]:
        merged: dict[str, dict] = {}
        for extra in ({}, {"employmentStatus": "Relieved"}):
            for e in self._employees(extra):
                merged[str(e.get("id") or e.get("employeeNumber") or id(e))] = e
        people = [p for p in (self.to_person(e) for e in merged.values()) if p]
        if merged and not people:
            raise ConnectorError("Keka returned employees but none had a work email. Field mapping needs updating.")
        return people
