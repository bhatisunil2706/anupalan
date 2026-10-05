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
