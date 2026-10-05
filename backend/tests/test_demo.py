"""Demo seed: every login works under RLS and each company only sees its own data."""
from app.services import demo
from tests.conftest import make_client


def _login(email):
    c = make_client()
    r = c.post("/api/auth/login", json={"email": email, "password": demo.DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["mfa_required"] is False
    return c


def test_seed_demo_companies(db):
    result = demo.seed(db)
    assert [o["org"] for o in result] == [c["name"] for c in demo.COMPANIES]

    priya = _login("priya@paisasetu.example")
    dash = priya.get("/api/dashboard")
    assert dash.status_code == 200, dash.text
    controls = priya.get("/api/controls").json()
    assert sum(c["status"] == "implemented" for c in controls) > 20
    assert len(priya.get("/api/vendors").json()) == 5
    assert priya.get("/api/consent/summary").json()["granted_30d"] > 50
    assert priya.get("/api/training/report").json()["people"]
    assert priya.get("/api/org/audit-log/verify").json()["ok"] is True

    auditor = _login("kavya@paisasetu.example")
    reqs = auditor.get("/api/audit/requests").json()
    assert {r["status"] for r in reqs} == {"submitted", "open"}
    assert auditor.get("/api/audit/frameworks/iso27001/matrix.xlsx").status_code == 200

    rajesh = _login("rajesh@kiranakart.example")
    names = {v["name"] for v in rajesh.get("/api/vendors").json()}
    assert "Razorpay" not in names and "Shiprocket" in names
    other_vendor = priya.get("/api/vendors").json()[0]["id"]
    assert rajesh.get(f"/api/vendors/{other_vendor}/detail").status_code == 404
