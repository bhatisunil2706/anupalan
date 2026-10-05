"""Darwinbox HR (beta).

Darwinbox exposes per-customer "master API" endpoints that the customer's Darwinbox admin enables, authenticated with
basic auth plus an API key and dataset key in the body. The field names below follow the commonly configured
employee master dataset and are mapped defensively; confirm against the customer's dataset before general release.
"""
import httpx

from app.integrations.base import Connector, ConnectorError, Field, PersonRecord, guarded_base_url


def _pick(d: dict, *keys) -> str:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return str(v).strip()
    return ""


class DarwinboxConnector(Connector):
    provider = "darwinbox"
    name = "Darwinbox"
    category = "HR"
    beta = True
    description = "Imports employees, managers, joining and exit dates for leaver checks and access reviews."
    setup_help = (
        "Ask your Darwinbox admin to enable the Employee master API (Settings > Integrations > API) and share the "
        "API username and password, API key and dataset key. Enter your Darwinbox domain, e.g. acme.darwinbox.in."
    )
    provides_people = True
    fields = [
        Field("domain", "Darwinbox domain", help="For example acme.darwinbox.in"),
        Field("username", "API username"),
        Field("password", "API password", secret=True),
        Field("api_key", "API key", secret=True),
        Field("dataset_key", "Employee dataset key", secret=True),
    ]
    tests = []

    def __init__(self, config: dict, secrets: dict, client: httpx.Client | None = None):
        super().__init__(config, secrets)
        self.base = guarded_base_url(config.get("domain", ""), allowed_suffixes=(".darwinbox.in", ".darwinbox.com",
                                                                                 ".darwinbox.io"))
        self.client = client or httpx.Client(timeout=60)

    def _fetch(self) -> list[dict]:
        r = self.client.post(f"{self.base}/masterapi/employee", auth=(self.config.get("username", ""),
                                                                      self.secrets.get("password", "")),
                             json={"api_key": self.secrets.get("api_key", ""),
                                   "datasetKey": self.secrets.get("dataset_key", "")})
        if r.status_code in (401, 403):
            raise ConnectorError("Darwinbox rejected the API credentials.")
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict) and str(body.get("status")) in ("0", "false", "error"):
            raise ConnectorError(f"Darwinbox returned an error: {str(body.get('message', ''))[:200]}")
        rows = body.get("employee_data") or body.get("data") or [] if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise ConnectorError("Unexpected response from Darwinbox; check the dataset key.")
        return rows

    def verify(self) -> None:
        self._fetch()

    def list_people(self) -> list[PersonRecord]:
        from app.services.people import infer_status, parse_date  # avoid an import cycle

        out = []
        for e in self._fetch():
            email = _pick(e, "company_email_id", "official_email", "email", "work_email").lower()
            if "@" not in email:
                continue
            exit_date = parse_date(_pick(e, "date_of_exit", "exit_date", "last_working_day", "date_of_relieving"))
            raw_status = _pick(e, "employee_status", "status", "employment_status")
            out.append(PersonRecord(
                email=email,
                full_name=_pick(e, "full_name", "employee_name") or
                f"{_pick(e, 'first_name')} {_pick(e, 'last_name')}".strip(),
                employee_id=_pick(e, "employee_id", "emp_id"), department=_pick(e, "department", "department_name"),
                title=_pick(e, "designation", "designation_name", "job_title"),
                manager_email=_pick(e, "direct_manager_email", "reporting_manager_email", "manager_email").lower(),
                status=infer_status(raw_status, exit_date), join_date=parse_date(_pick(e, "date_of_joining", "doj")),
                exit_date=exit_date))
        return out
