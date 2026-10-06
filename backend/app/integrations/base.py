from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Field:
    name: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""
    default: str = ""
    multiline: bool = False


@dataclass
class TestDef:
    key: str
    title: str
    control_codes: list[str]
    description: str = ""


@dataclass
class CheckResult:
    key: str
    status: str  # pass | fail | error
    summary: str
    details: dict = field(default_factory=dict)


@dataclass
class AccountRecord:
    """A user account in a connected system (identity inventory)."""

    external_id: str
    email: str = ""
    name: str = ""
    is_admin: bool = False
    is_active: bool = True
    mfa_enabled: bool | None = None
    last_login_at: datetime | None = None


@dataclass
class PersonRecord:
    """An employee from an HR system."""

    email: str
    full_name: str = ""
    employee_id: str = ""
    department: str = ""
    title: str = ""
    manager_email: str = ""
    status: str = "active"  # active | exited
    join_date: date | None = None
    exit_date: date | None = None


class ConnectorError(Exception):
    """Raised for credential or connectivity problems; message is shown to the user."""


class Connector:
    provider: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    setup_help: str = ""
    beta: bool = False
    fields: list[Field] = []
    tests: list[TestDef] = []
    provides_accounts: bool = False  # implements list_accounts()
    provides_people: bool = False  # implements list_people()

    def __init__(self, config: dict, secrets: dict):
        self.config = config
        self.secrets = secrets

    def verify(self) -> None:
        """Check credentials work. Raise ConnectorError with a helpful message if not."""
        raise NotImplementedError

    def run(self) -> list[CheckResult]:
        return []

    def list_accounts(self) -> list[AccountRecord]:
        return []

    def list_people(self) -> list[PersonRecord]:
        return []

    @classmethod
    def test_def(cls, key: str) -> TestDef:
        return next(t for t in cls.tests if t.key == key)

    @classmethod
    def describe(cls) -> dict:
        return {
            "provider": cls.provider,
            "name": cls.name,
            "description": cls.description,
            "category": cls.category,
            "setup_help": cls.setup_help,
            "beta": cls.beta,
            "provides_accounts": cls.provides_accounts,
            "provides_people": cls.provides_people,
            "fields": [f.__dict__ for f in cls.fields],
            "tests": [t.__dict__ for t in cls.tests],
        }


def guarded_base_url(value: str, *, allowed_suffixes: tuple[str, ...] = (), default: str = "") -> str:
    """Validate a customer-supplied API base URL (https only, no private networks in production)."""
    from app.net_guard import UnsafeTargetError, check_url

    raw = (value or default).strip()
    if raw and "://" not in raw:
        raw = "https://" + raw
    try:
        return check_url(raw, allowed_suffixes=allowed_suffixes)
    except UnsafeTargetError as e:
        raise ConnectorError(str(e)) from e


def link_next(response) -> str | None:
    """Return the rel="next" URL from an RFC 8288 Link header (Okta, GitLab)."""
    for part in response.headers.get("link", "").split(","):
        if 'rel="next"' in part:
            return part[part.find("<") + 1:part.find(">")]
    return None


SEVERITY_ALIASES = {"critical": "critical", "high": "high", "4": "critical", "3": "high", "crit": "critical"}


def sla_result(key: str, findings: list[dict], config: dict) -> CheckResult:
    """Shared vulnerability SLA check. findings: [{severity, created_at (ISO), name}]. Fails when a critical or
    high finding has been open longer than the fix deadline (defaults: critical 15 days, high 30 days)."""
    from datetime import datetime, timezone

    limits = {"critical": int(config.get("critical_days") or 15), "high": int(config.get("high_days") or 30)}
    now = datetime.now(timezone.utc)
    overdue, open_counts = [], {"critical": 0, "high": 0}
    for f in findings:
        sev = SEVERITY_ALIASES.get(str(f.get("severity", "")).lower())
        if sev not in limits:
            continue
        open_counts[sev] += 1
        created = f.get("created_at")
        try:
            opened = datetime.fromisoformat(str(created).replace("Z", "+00:00")) if created else None
        except ValueError:
            opened = None
        if opened and opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
        if opened and (now - opened).days > limits[sev]:
            overdue.append({"name": f.get("name", ""), "severity": sev, "days_open": (now - opened).days})
    summary_open = f"{open_counts['critical']} critical and {open_counts['high']} high open"
    if overdue:
        return CheckResult(key, "fail", f"{len(overdue)} past the fix deadline ({summary_open})",
                           {"overdue": sorted(overdue, key=lambda x: -x["days_open"])[:200], "limits_days": limits})
    return CheckResult(key, "pass", f"Nothing past the fix deadline ({summary_open})", {"limits_days": limits})
