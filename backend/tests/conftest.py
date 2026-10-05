import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/app_test")
os.environ["ENVIRONMENT"] = "test"
os.environ["LOAD_CONTENT_ON_STARTUP"] = "false"
os.environ.setdefault("STORAGE_DIR", "/tmp/anupalan-test-storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.content import load_content  # noqa: E402

GLOBAL_TABLES = {"frameworks", "requirements", "control_templates", "mappings", "policy_templates"}


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        load_content(db)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tenant_data():
    yield
    tables = [t.name for t in Base.metadata.sorted_tables if t.name not in GLOBAL_TABLES]
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " CASCADE"))
    from app.api.routes import auth

    auth._FAILED.clear()


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def make_client() -> TestClient:
    return TestClient(app)


def signup(client: TestClient, email="owner@acme.in", org="Acme", name="Asha Rao") -> dict:
    r = client.post("/api/auth/signup", json={"full_name": name, "email": email,
                                              "password": "correct-horse-1", "org_name": org})
    assert r.status_code == 201, r.text
    return r.json()


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
    onboard(client)
    return client
