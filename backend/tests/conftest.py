"""Test setup. Tables are created by an admin role; the app under test connects with a restricted role, so
PostgreSQL row-level security is enforced exactly as in production."""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ADMIN_URL = os.environ.get("TEST_ADMIN_DATABASE_URL") or os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/app_test")
RUNTIME_ROLE, RUNTIME_PASSWORD = "app_test_runtime", "test-runtime-password"

_admin = create_engine(ADMIN_URL, future=True)
with _admin.begin() as conn:
    if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNTIME_ROLE}).first():
        conn.execute(text(f"CREATE ROLE {RUNTIME_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{RUNTIME_PASSWORD}'"))

os.environ["DATABASE_URL"] = make_url(ADMIN_URL).set(username=RUNTIME_ROLE, password=RUNTIME_PASSWORD).render_as_string(
    hide_password=False)
os.environ["ENVIRONMENT"] = "test"
os.environ["LOAD_CONTENT_ON_STARTUP"] = "false"
os.environ["PASSWORD_BREACH_CHECK"] = "false"
os.environ.setdefault("STORAGE_DIR", "/tmp/pramaanly-test-storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import rls  # noqa: E402
from app.db import Base, engine, system_session  # noqa: E402
from app.main import app  # noqa: E402
from app.services.content import load_content  # noqa: E402

PASSWORD = "Correct-Horse-Battery-77"
GLOBAL_TABLES = rls.CONTENT_TABLES


@pytest.fixture(scope="session", autouse=True)
def database():
    with _admin.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(_admin)
    with _admin.begin() as conn:
        rls.apply_policies(conn)
        rls.grant_runtime(conn, RUNTIME_ROLE)
    with Session(_admin) as db:
        load_content(db)
    yield
    engine.dispose()
    _admin.dispose()


@pytest.fixture(autouse=True)
def clean_tenant_data():
    yield
    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in GLOBAL_TABLES]
    with _admin.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " CASCADE"))
    from app import ratelimit

    ratelimit.store().clear()


@pytest.fixture
def db():
    """Trusted session that sees every organisation (like the worker). The API itself never gets this."""
    with system_session() as s:
        yield s


@pytest.fixture
def admin_engine():
    return _admin


def make_client() -> TestClient:
    client = TestClient(app)

    def hook(request):
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and "x-csrf-token" not in request.headers:
            token = client.cookies.get("csrf")
            if token:
                request.headers["X-CSRF-Token"] = token

    client.event_hooks["request"] = [hook]
    return client


def signup(client: TestClient, email="owner@acme.in", org="Acme", name="Asha Rao", password=PASSWORD) -> dict:
    r = client.post("/api/auth/signup", json={"full_name": name, "email": email, "password": password,
                                              "org_name": org})
    assert r.status_code == 201, r.text
    return r.json()


def verify_email(email: str) -> None:
    with _admin.begin() as conn:
        conn.execute(text("UPDATE users SET email_verified_at = now() WHERE email = :e"), {"e": email})


def onboard(client: TestClient, frameworks=("dpdp", "certin", "iso27001", "soc2"), profile=None) -> dict:
    r = client.post("/api/org/onboarding", json={"sector": "SaaS", "employee_count": "51-200",
                                                 "profile": profile or {}, "framework_codes": list(frameworks)})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def client():
    return make_client()


@pytest.fixture
def owner(client):
    signup(client)
    verify_email("owner@acme.in")
    onboard(client)
    return client
