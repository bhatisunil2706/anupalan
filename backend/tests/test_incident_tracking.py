"""Incident reporting by anyone, the incident timeline, followers and threaded email updates."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import Notification
from app.services import notify
from tests.conftest import make_client, onboard, signup, verify_email

PW = "Quartz-Lantern-Harbor-42"


def join(owner, email, role="member", name=None):
    inv = owner.post("/api/org/invitations", json={"email": email, "role": role, "access_days": 30}).json()
    c = make_client()
    r = c.post("/api/auth/invitations/accept", json={"token": inv["invite_url"].rsplit("/", 1)[1],
                                                     "full_name": name or email.split("@")[0].title(),
                                                     "password": PW})
    assert r.status_code == 200, r.text
    return c


def report(client, **kw):
    body = {"title": "Phishing email clicked", "description": "Finance clicked a fake invoice link.",
            "severity": "sev2", "detected_at": datetime.now(timezone.utc).isoformat(), **kw}
    r = client.post("/api/incidents", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def thread_mail(db, inc_id):
    return db.scalars(select(Notification).where(Notification.thread == f"incident-{inc_id}")
                      .order_by(Notification.created_at)).all()


def test_member_reports_and_everyone_tracks_it_by_email(owner, db):
    member = join(owner, "ravi@acme.in", name="Ravi")
    inc = report(member, certin_reportable=True)
    assert inc["reported_by"]["email"] == "ravi@acme.in"

    act = member.get(f"/api/incidents/{inc['id']}/activity").json()
    assert {f["email"] for f in act["followers"]} == {"owner@acme.in", "ravi@acme.in"}
    assert act["following"] and act["events"][0]["kind"] == "reported"

    mails = thread_mail(db, inc["id"])
    assert len(mails) == 1
    first = mails[0]
    # The reporter gets a receipt in the same thread; admins are told; Slack/Teams too.
    assert set(first.recipients) == {"owner@acme.in", "ravi@acme.in"} and first.broadcast
    assert first.subject == f"INC-{inc['number']}: Phishing email clicked"
    assert "CERT-In report within 6 hours" in first.body

    # The owner posts updates and changes status: each is emailed to followers except the person who did it.
    owner.post(f"/api/incidents/{inc['id']}/updates", json={"message": "Reset Ravi's password; no MFA bypass."})
    owner.patch(f"/api/incidents/{inc['id']}", json={"status": "contained", "severity": "sev1"})
    owner.patch(f"/api/incidents/{inc['id']}", json={"certin_reported_at": datetime.now(timezone.utc).isoformat()})
    owner.patch(f"/api/incidents/{inc['id']}", json={"root_cause": "Lookalike domain."})  # timeline only
    db.expire_all()
    mails = thread_mail(db, inc["id"])
    assert len(mails) == 5
    assert all(m.subject == first.subject for m in mails)  # one subject line, so one conversation
    later = mails[1:]
    assert all(m.recipients == ["ravi@acme.in"] for m in later)
    bodies = "\n".join(m.title + m.body for m in later)
    assert "Reset Ravi's password" in bodies and "Open to Contained" in bodies and "SEV-2 to SEV-1" in bodies
    assert "Reported to CERT-In" in bodies and "Lookalike" not in bodies

    kinds = [e["kind"] for e in owner.get(f"/api/incidents/{inc['id']}/activity").json()["events"]]
    assert kinds == ["details", "regulatory", "severity", "status", "note", "reported"]


def test_email_thread_headers(owner, db):
    inc = report(owner)
    owner.post(f"/api/incidents/{inc['id']}/updates", json={"message": "Investigating."})
    mails = thread_mail(db, inc["id"])
    h1, h2 = notify.thread_headers(db, mails[0]), notify.thread_headers(db, mails[1])
    root = f"<incident-{inc['id']}@{notify.mail_domain()}>"
    assert h1 == {"Message-ID": root}
    assert h2["In-Reply-To"] == root and h2["References"] == root and h2["Message-ID"] != root


def test_follow_unfollow_and_new_lead(owner, db):
    member = join(owner, "meera@acme.in", name="Meera")
    other = join(owner, "kiran@acme.in", name="Kiran")
    inc = report(owner)
    path = f"/api/incidents/{inc['id']}"
    assert not member.get(path + "/activity").json()["following"]
    assert member.post(path + "/follow").json()["following"]
    owner.post(path + "/updates", json={"message": "Update one"})
    assert member.delete(path + "/follow").json() == {"following": False}
    owner.post(path + "/updates", json={"message": "Update two"})
    # Assigning a lead makes them a follower.
    kiran = next(m["user"] for m in owner.get("/api/org/members").json() if m["user"]["email"] == "kiran@acme.in")
    owner.patch(path, json={"lead_id": kiran["id"]})
    assert other.get(path + "/activity").json()["following"]
    db.expire_all()
    mails = {m.body.split("\n")[0]: m.recipients for m in thread_mail(db, inc["id"])}
    assert "meera@acme.in" in mails["Update one"] and "meera@acme.in" not in mails["Update two"]
    assert "kiran@acme.in" in mails["Kiran is now the incident lead."]


def test_permissions_and_isolation(owner):
    auditor = join(owner, "aud@firm.in", role="auditor")
    inc = report(owner)
    path = f"/api/incidents/{inc['id']}"
    assert auditor.post("/api/incidents", json={"title": "x", "detected_at": inc["detected_at"]}).status_code == 403
    assert auditor.post(path + "/updates", json={"message": "hi"}).status_code == 403
    assert auditor.get(path + "/activity").status_code == 200
    assert owner.post(path + "/updates", json={"message": ""}).status_code == 422

    other = make_client()
    signup(other, email="boss@globex.in", org="Globex")
    verify_email("boss@globex.in")
    onboard(other)
    for method, url in (("get", path + "/activity"), ("post", path + "/follow")):
        assert getattr(other, method)(url).status_code == 404
    assert other.post(path + "/updates", json={"message": "x"}).status_code == 404


def test_timeline_is_append_only(owner):
    report(owner)
    with SessionLocal() as s:
        with pytest.raises(Exception, match="permission denied"):
            s.execute(text("UPDATE incident_events SET message = 'rewritten'"))
    with SessionLocal() as s:
        with pytest.raises(Exception, match="permission denied"):
            s.execute(text("DELETE FROM incident_events"))


def test_delivered_email_carries_thread_headers(owner, db, monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg)

    settings = notify.get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    inc = report(owner, title="Ransomware note on file server")
    owner.post(f"/api/incidents/{inc['id']}/updates", json={"message": "Isolated the server."})
    notify.deliver_pending(db)
    mails = [m for m in sent if "INC-" in m["Subject"]]
    assert len(mails) == 2
    assert {m["Subject"] for m in mails} == {f"[Acme] INC-{inc['number']}: Ransomware note on file server"}
    assert mails[1]["In-Reply-To"] == mails[0]["Message-ID"]
    assert "Isolated the server." in mails[1].get_content()


def test_regulator_clocks(owner, db):
    from datetime import timedelta

    from app.services.reminders import incident_reminders

    # Suggested regulators follow the organisation's frameworks.
    assert not any(r["suggested"] for r in owner.get("/api/incident-regulators").json())
    owner.post("/api/frameworks/rbi_pso/enable")
    owner.post("/api/frameworks/ifsca_cyber/enable")
    sugg = {r["key"]: r["suggested"] for r in owner.get("/api/incident-regulators").json()}
    assert sugg == {"rbi": True, "sebi": False, "irdai": False, "ifsca": True}

    detected = datetime.now(timezone.utc) - timedelta(hours=5)
    inc = report(owner, regulators=["rbi"], detected_at=detected.isoformat())
    clocks = {c["key"]: c for c in inc["regulator_clocks"]}
    assert set(clocks) == {"rbi"} and clocks["rbi"]["reported_at"] is None
    assert abs(datetime.fromisoformat(clocks["rbi"]["due_at"]) - (detected + timedelta(hours=6))) < timedelta(seconds=1)
    first = thread_mail(db, inc["id"])[0]
    assert "Report to RBI" in first.body

    path = f"/api/incidents/{inc['id']}"
    assert owner.patch(path, json={"regulators": ["rbi", "nasa"]}).status_code == 422
    assert owner.patch(path, json={"regulator_reported": {"rbi": "2026-11-03T10:00:00"}}).status_code == 422

    # Dashboard and reminders know about the clock (due within the hour).
    dl = owner.get("/api/dashboard").json()["deadlines"]
    assert any(d["kind"] == "regulator" and "Report to RBI" in d["label"] for d in dl)
    from app.models import Incident, Organization

    org = db.scalar(select(Organization))
    incident_reminders(db, org, datetime.now(timezone.utc))
    db.commit()
    assert any("Report to RBI due soon" in m.title for m in thread_mail(db, inc["id"]))

    # Add IFSCA: three clocks; record and correct reports.
    r = owner.patch(path, json={"regulators": ["rbi", "ifsca"]}).json()
    assert [c["key"] for c in r["regulator_clocks"]] == ["rbi", "ifsca", "ifsca_interim", "ifsca_rca"]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    r = owner.patch(path, json={"regulator_reported": {"rbi": now.isoformat()}}).json()
    assert next(c for c in r["regulator_clocks"] if c["key"] == "rbi")["reported_at"]
    r = owner.patch(path, json={"regulator_reported": {"ifsca": now.isoformat()}}).json()
    assert db.get(Incident, inc["id"]) is not None
    assert all(c["reported_at"] for c in r["regulator_clocks"] if c["key"] in ("rbi", "ifsca"))
    r = owner.patch(path, json={"regulator_reported": {"rbi": None}}).json()
    assert not next(c for c in r["regulator_clocks"] if c["key"] == "rbi")["reported_at"]

    msgs = [e["message"] for e in owner.get(path + "/activity").json()["events"]]
    assert any(m.startswith("Marked as reportable to IFSCA") for m in msgs)
    assert any(m.startswith("Report to RBI done at") for m in msgs)
    assert any(m.startswith("Cleared the recorded time for: Report to RBI") for m in msgs)
    dl = owner.get("/api/dashboard").json()["deadlines"]
    assert any("Report to RBI" in d["label"] for d in dl) and not any("Initial report to IFSCA" in d["label"] for d in dl)
