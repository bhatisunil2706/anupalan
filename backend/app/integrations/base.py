from dataclasses import dataclass, field


@dataclass
class Field:
    name: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""
    default: str = ""


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


class ConnectorError(Exception):
    """Raised for credential or connectivity problems; message is shown to the user."""


class Connector:
    provider: str = ""
    name: str = ""
    description: str = ""
    category: str = ""
    setup_help: str = ""
    fields: list[Field] = []
    tests: list[TestDef] = []

    def __init__(self, config: dict, secrets: dict):
        self.config = config
        self.secrets = secrets

    def verify(self) -> None:
        """Check credentials work. Raise ConnectorError with a helpful message if not."""
        raise NotImplementedError

    def run(self) -> list[CheckResult]:
        raise NotImplementedError

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
            "fields": [f.__dict__ for f in cls.fields],
            "tests": [t.__dict__ for t in cls.tests],
        }
