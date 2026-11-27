"""Security behaviour: sessions, CSRF, MFA, password reset, lockout, RLS, audit chain, encrypted evidence, SSO."""
import json
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pyotp
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select, text

from app.config import get_settings
from app.db import SessionLocal, set_tenant
from app.models import Control, Evidence, Organization
from app.services import notify
from tests.conftest import PASSWORD, make_client, onboard, signup, verify_email


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "send_email", lambda to, subject, body: sent.append(
        {"to": to, "subject": subject, "body": body}))
    return sent


def _link_token(mail: dict) -> str:
    return mail["body"].split("token=")[1].split()[0]


def _enable_mfa(client) -> tuple[str, list[str]]:
    setup = client.post("/api/auth/mfa/setup").json()
    assert setup["qr"].startswith("data:image/svg+xml;base64,")
    secret = setup["secret"]
    codes = client.post("/api/auth/mfa/enable", json={"code": pyotp.TOTP(secret).now()}).json()["recovery_codes"]
    assert len(codes) == 10
    return secret, codes


def _next_code(secret: str) -> str:
    """A code for the next time step, so it isn't rejected as a replay of the one just used."""
    return pyotp.TOTP(secret).at(time.time() + 30)


# ---------------------------------------------------------------- sessions and CSRF


def test_session_is_opaque_server_side_and_revocable(client):
    signup(client)
    cookie = client.cookies.get("session")
    assert cookie and cookie.count(".") < 2  # not a JWT: nothing to decode or forge
    stolen = make_client()
    stolen.cookies.set("session", cookie)
    assert stolen.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert stolen.get("/api/auth/me").status_code == 401  # logout kills the session everywhere


def test_sessions_list_and_revoke_others(client):
    signup(client)
    second = make_client()
    second.post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    listed = client.get("/api/auth/sessions").json()
    assert len(listed) == 2 and sum(s["current"] for s in listed) == 1
    assert client.post("/api/auth/sessions/revoke-others").json()["revoked"] == 1
    assert second.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200


def test_csrf_and_origin_checks(owner):
    token = owner.cookies.get("csrf")
    assert owner.post("/api/risks", json={"title": "x"}, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    no_header = make_client()
    no_header.cookies.set("session", owner.cookies.get("session"))
    no_header.event_hooks["request"] = []
    assert no_header.post("/api/risks", json={"title": "x"}).status_code == 403
    assert owner.post("/api/risks", json={"title": "x"}, headers={"Origin": "https://evil.example",
                                                                 "X-CSRF-Token": token}).status_code == 403
    assert owner.post("/api/risks", json={"title": "ok"}).status_code == 201


def test_security_headers(owner):
    r = owner.get("/api/auth/me")
    for h in ("x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy",
              "x-request-id"):
        assert h in r.headers
    assert r.headers["cache-control"] == "no-store"


def test_idle_timeout(owner, admin_engine):
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE organizations SET session_idle_minutes = 5"))
        conn.execute(text("UPDATE user_sessions SET last_seen_at = now() - interval '6 minutes'"))
    assert owner.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------- passwords


def test_weak_and_personal_passwords_rejected(client):
    for pw in ("password123456", "qwertyuiop1234", "owner@acme.in2026", "AshaRaoAcme2026"):
        r = client.post("/api/auth/signup", json={"full_name": "Asha Rao", "email": "owner@acme.in",
                                                  "password": pw, "org_name": "Acme"})
        assert r.status_code in (400, 422), pw


def test_password_reset_flow(client, outbox):
    signup(client)
    other_device = make_client()
    other_device.post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    anon = make_client()
    assert anon.post("/api/auth/password/forgot", json={"email": "nobody@acme.in"}).status_code == 202
    assert anon.post("/api/auth/password/forgot", json={"email": "owner@acme.in"}).status_code == 202
    reset_mail = [m for m in outbox if "Reset your" in m["subject"]]
    assert len(reset_mail) == 1 and reset_mail[0]["to"] == ["owner@acme.in"]  # nothing sent for unknown email
    token = _link_token(reset_mail[0])
    assert anon.post("/api/auth/password/reset", json={"token": token, "password": "aaaaaaaaaaaa"}).status_code == 400
    new_pw = "Granite-Orchid-Teapot-19"
    assert anon.post("/api/auth/password/reset", json={"token": token, "password": new_pw}).status_code == 200
    assert anon.post("/api/auth/password/reset", json={"token": token, "password": new_pw}).status_code == 400
    assert other_device.get("/api/auth/me").status_code == 401  # all sessions revoked
    assert client.get("/api/auth/me").status_code == 401
    assert anon.post("/api/auth/login", json={"email": "owner@acme.in", "password": new_pw}).status_code == 200
    assert any("password was changed" in m["subject"] for m in outbox)


def test_change_password_requires_current(owner, outbox):
    r = owner.post("/api/auth/password/change", json={"current_password": "wrong", "new_password": "Granite-Orchid-Teapot-19"})
    assert r.status_code == 400
    r = owner.post("/api/auth/password/change", json={"current_password": PASSWORD,
                                                      "new_password": "Granite-Orchid-Teapot-19"})
    assert r.status_code == 204 and owner.get("/api/auth/me").status_code == 200


def test_account_lockout_does_not_reveal_accounts(client):
    signup(client)
    other = make_client()
    for _ in range(10):
        other.post("/api/auth/login", json={"email": "nobody@acme.in", "password": "x"})
    assert other.post("/api/auth/login", json={"email": "nobody@acme.in", "password": "x"}).status_code == 429


def test_email_verification_and_invite_gate(client, outbox):
    signup(client)
    onboard(client)
    assert client.get("/api/auth/me").json()["email_verified"] is False
    assert client.post("/api/org/invitations", json={"email": "x@acme.in"}).status_code == 403
    token = _link_token(next(m for m in outbox if "Confirm your email" in m["subject"]))
    assert make_client().post("/api/auth/email/verify", json={"token": token}).status_code == 200
    assert client.get("/api/auth/me").json()["email_verified"] is True
    assert client.post("/api/org/invitations", json={"email": "x@acme.in"}).status_code == 201


# ---------------------------------------------------------------- MFA


def test_mfa_login_flow_replay_and_recovery_codes(owner, outbox):
    secret, codes = _enable_mfa(owner)
    assert owner.get("/api/auth/mfa/status").json()["recovery_codes_remaining"] == 10
    c = make_client()
    r = c.post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    assert r.json() == {"mfa_required": True, "me": None}
    assert c.get("/api/auth/me").status_code == 401  # half-signed-in session can't use the app
    assert c.post("/api/auth/mfa/verify", json={"code": "000000"}).status_code == 401
    code = _next_code(secret)
    assert c.post("/api/auth/mfa/verify", json={"code": code}).status_code == 200
    assert c.get("/api/auth/me").status_code == 200

    replay = make_client()
    replay.post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    assert replay.post("/api/auth/mfa/verify", json={"code": code}).status_code == 401  # same code can't be reused
    assert replay.post("/api/auth/mfa/verify", json={"code": codes[0].lower().replace("-", "")}).status_code == 200

    again = make_client()
    again.post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    assert again.post("/api/auth/mfa/verify", json={"code": codes[0]}).status_code == 401  # recovery codes are single use
    assert owner.get("/api/auth/mfa/status").json()["recovery_codes_remaining"] == 9


def test_mfa_attempts_are_limited(owner):
    _enable_mfa(owner)
    c = make_client()
    c.post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    for _ in range(5):
        assert c.post("/api/auth/mfa/verify", json={"code": "123456"}).status_code == 401
    assert c.post("/api/auth/mfa/verify", json={"code": "123456"}).status_code == 429
    assert c.post("/api/auth/mfa/verify", json={"code": "123456"}).status_code == 401  # challenge is gone


def test_org_mfa_policy(owner):
    inv = owner.post("/api/org/invitations", json={"email": "m@acme.in", "role": "member"}).json()
    member = make_client()
    member.post("/api/auth/invitations/accept", json={"token": inv["invite_url"].rsplit("/", 1)[1],
                                                      "full_name": "Mem Ber", "password": "Saffron-Bicycle-Ladder-31"})
    assert owner.put("/api/org/security", json={"require_mfa": True}).status_code == 400  # admin needs MFA first
    _enable_mfa(owner)
    assert owner.put("/api/org/security", json={"require_mfa": True}).json()["require_mfa"] is True
    assert owner.get("/api/controls").status_code == 200
    r = member.get("/api/controls")
    assert r.status_code == 403 and "MFA_SETUP_REQUIRED" in r.json()["detail"]
    assert member.get("/api/auth/me").json()["mfa_setup_required"] is True
    _enable_mfa(member)
    assert member.get("/api/controls").status_code == 200
    r = member.post("/api/auth/mfa/disable", json={"password": "Saffron-Bicycle-Ladder-31", "code": "000000"})
    assert r.status_code == 400


# ---------------------------------------------------------------- row-level security


def test_rls_blocks_cross_tenant_reads_and_writes(owner):
    other = make_client()
    signup(other, "b@other.in", "Other")
    onboard(other, frameworks=("dpdp",))
    with SessionLocal() as db:  # the app's own restricted connection
        orgs = {o.name: o.id for o in db.scalars(select(Organization))}
        assert orgs == {}  # no tenant context: nothing is visible at all
        set_tenant(db, rls_bypass=True)
        ids = {o.name: o.id for o in db.scalars(select(Organization))}
    with SessionLocal() as db:
        set_tenant(db, org_id=ids["Acme"])
        controls = db.scalars(select(Control)).all()  # deliberately no org filter
        assert controls and {c.org_id for c in controls} == {ids["Acme"]}
        assert db.get(Organization, ids["Other"]) is None
        db.add(Control(org_id=ids["Other"], code="EVIL-1", title="x"))
        with pytest.raises(Exception, match="row-level security"):
            db.flush()


# ---------------------------------------------------------------- audit chain


def test_audit_chain_detects_tampering(owner, admin_engine):
    owner.post("/api/risks", json={"title": "Phishing"})
    ok = owner.get("/api/org/audit-log/verify").json()
    assert ok["ok"] and ok["entries"] >= 3
    with SessionLocal() as db:  # the runtime role can't rewrite history at all
        with pytest.raises(Exception, match="permission denied"):
            db.execute(text("UPDATE audit_logs SET action = 'nothing'"))
    with admin_engine.begin() as conn:  # a database admin can, but it's detected
        conn.execute(text("UPDATE audit_logs SET detail = '{\"title\": \"Edited\"}' WHERE action = 'risk.created'"))
    broken = owner.get("/api/org/audit-log/verify").json()
    assert not broken["ok"] and broken["broken_at"] is not None


# ---------------------------------------------------------------- evidence storage


def test_evidence_is_encrypted_at_rest_and_validated(owner, db):
    ctl = owner.get("/api/controls").json()[0]
    secret_text = b"%PDF-1.4 CONFIDENTIAL-ACCESS-REVIEW"
    r = owner.post(f"/api/controls/{ctl['id']}/evidence", data={"title": "Review", "kind": "file"},
                   files={"file": ("review.pdf", secret_text, "application/pdf")})
    assert r.status_code == 201, r.text
    ev = db.get(Evidence, uuid.UUID(r.json()["id"]))
    raw = (Path(get_settings().storage_dir).resolve() / ev.file_key).read_bytes()
    assert raw.startswith(b"ANPE1") and b"CONFIDENTIAL" not in raw
    d = owner.get(f"/api/evidence/{ev.id}/download")
    assert d.content == secret_text
    assert d.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in d.headers["content-security-policy"]
    fake = owner.post(f"/api/controls/{ctl['id']}/evidence", data={"title": "x", "kind": "file"},
                      files={"file": ("evil.pdf", b"<script>alert(1)</script>", "application/pdf")})
    assert fake.status_code == 400
    html = owner.post(f"/api/controls/{ctl['id']}/evidence", data={"title": "x", "kind": "file"},
                      files={"file": ("page.html", b"<html></html>", "text/html")})
    assert html.status_code == 400


def test_storage_keys_are_bound_to_org():
    from app.services import storage

    a, b = uuid.uuid4(), uuid.uuid4()
    blob = storage.encrypt(a, f"{a}/f.txt", b"hello")
    assert storage.decrypt(a, f"{a}/f.txt", blob) == b"hello"
    from cryptography.exceptions import InvalidTag

    with pytest.raises(InvalidTag):
        storage.decrypt(b, f"{a}/f.txt", blob)  # another org's key can't open it
    with pytest.raises(InvalidTag):
        storage.decrypt(a, f"{a}/other.txt", blob)  # moved to a different path: rejected


# ---------------------------------------------------------------- time-limited access


def test_auditor_access_expires(owner, admin_engine):
    inv = owner.post("/api/org/invitations", json={"email": "aud@firm.in", "role": "auditor", "access_days": 14}).json()
    aud = make_client()
    r = aud.post("/api/auth/invitations/accept", json={"token": inv["invite_url"].rsplit("/", 1)[1],
                                                       "full_name": "Ext Auditor", "password": "Harbor-Violet-Compass-63"})
    assert r.json()["access_expires_at"] is not None
    assert aud.get("/api/controls").status_code == 200
    with admin_engine.begin() as conn:
        conn.execute(text("UPDATE memberships SET expires_at = now() - interval '1 minute' WHERE role = 'auditor'"))
    assert aud.get("/api/controls").status_code == 403


# ---------------------------------------------------------------- SSO


@pytest.fixture
def idp(monkeypatch):
    """A fake OpenID provider with its own RSA key."""
    from app.services import sso

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://idp.example.com"
    state = {"nonce": None, "email": "dev@acme.in", "email_verified": True, "aud": "client-123"}
    doc = {"issuer": issuer, "authorization_endpoint": f"{issuer}/authorize", "token_endpoint": f"{issuer}/token",
           "jwks_uri": f"{issuer}/jwks"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json=doc)
        if request.url.path == "/token":
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            assert form["code_verifier"] and form["client_secret"] == "s3cret"
            now = int(time.time())
            claims = {"iss": issuer, "aud": state["aud"], "sub": "u1", "iat": now, "exp": now + 300,
                      "nonce": state["nonce"], "email": state["email"], "email_verified": state["email_verified"],
                      "name": "Dev Eloper"}
            return httpx.Response(200, json={"id_token": jwt.encode(claims, key, algorithm="RS256")})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(sso, "_discovery_cache", {})
    real_discovery, real_start, real_complete = sso.discovery, sso.start, sso.complete
    monkeypatch.setattr(sso, "discovery", lambda iss, c=None: real_discovery(iss, client))
    monkeypatch.setattr(sso, "signing_key", lambda uri, tok: key.public_key())
    monkeypatch.setattr(sso, "txt_records", lambda d: [f"{sso.DNS_PREFIX}{state.get('dns_token', '')}"])

    def start(db, email, c=None):
        url = real_start(db, email, client)
        state["nonce"] = dict(httpx.URL(url).params)["nonce"]
        state["state"] = dict(httpx.URL(url).params)["state"]
        return url

    monkeypatch.setattr(sso, "start", start)
    monkeypatch.setattr(sso, "complete", lambda db, s, code, c=None: real_complete(db, s, code, client))
    state["issuer"] = issuer
    return state


def _setup_sso(owner, idp, *, enforced=False, jit=True):
    d = owner.post("/api/org/domains", json={"domain": "acme.in"}).json()
    idp["dns_token"] = d["txt_record"].split("=", 1)[1]
    assert owner.post(f"/api/org/domains/{d['id']}/verify").json()["verified_at"]
    r = owner.put("/api/org/sso", json={"provider": "oidc", "issuer": idp["issuer"], "client_id": "client-123",
                                        "client_secret": "s3cret", "enabled": True, "enforced": enforced,
                                        "jit_provisioning": jit})
    assert r.status_code == 200, r.text


def _sso_login(email: str, idp):
    c = make_client()
    r = c.post("/api/auth/sso/start", json={"email": email})
    assert r.status_code == 200, r.text
    assert "code_challenge" in r.json()["redirect_url"]
    return c, c.get(f"/api/auth/sso/callback?state={idp['state']}&code=abc", follow_redirects=False)


def test_sso_requires_verified_domain(owner, idp):
    r = owner.put("/api/org/sso", json={"provider": "oidc", "issuer": idp["issuer"], "client_id": "client-123",
                                        "client_secret": "s3cret", "enabled": True})
    assert r.status_code == 400 and "Verify" in r.json()["detail"]
    assert owner.post("/api/org/domains", json={"domain": "gmail.com"}).status_code == 400


def test_sso_login_with_jit_and_checks(owner, idp):
    _setup_sso(owner, idp)
    c, r = _sso_login("dev@acme.in", idp)
    assert r.status_code == 303 and r.headers["location"] == "/dashboard"
    me = c.get("/api/auth/me").json()
    assert me["user"]["email"] == "dev@acme.in" and me["role"] == "member" and me["auth_method"] == "sso"
    # The callback state can't be replayed.
    replay = make_client().get(f"/api/auth/sso/callback?state={idp['state']}&code=abc", follow_redirects=False)
    assert "sso_error" in replay.headers["location"]
    # Nonce mismatch, unverified email and other domains are all rejected.
    for tweak in ({"email_verified": False}, {"email": "dev@evil.in"}, {"aud": "someone-else"}):
        idp.update({"email": "dev@acme.in", "email_verified": True, "aud": "client-123"} | tweak)
        _, r = _sso_login("dev@acme.in", idp)
        assert "sso_error" in r.headers["location"], tweak


def test_sso_enforcement_blocks_password_login_except_owner(owner, idp):
    inv = owner.post("/api/org/invitations", json={"email": "m@acme.in", "role": "member"}).json()
    make_client().post("/api/auth/invitations/accept", json={"token": inv["invite_url"].rsplit("/", 1)[1],
                                                             "full_name": "Mem Ber",
                                                             "password": "Saffron-Bicycle-Ladder-31"})
    _setup_sso(owner, idp, enforced=True)
    r = make_client().post("/api/auth/login", json={"email": "m@acme.in", "password": "Saffron-Bicycle-Ladder-31"})
    assert r.status_code == 403 and "single sign-on" in r.json()["detail"]
    r = make_client().post("/api/auth/login", json={"email": "owner@acme.in", "password": PASSWORD})
    assert r.status_code == 200  # break-glass owner


def test_domain_cannot_be_claimed_twice(owner, idp):
    d = owner.post("/api/org/domains", json={"domain": "acme.in"}).json()
    idp["dns_token"] = d["txt_record"].split("=", 1)[1]
    owner.post(f"/api/org/domains/{d['id']}/verify")
    other = make_client()
    signup(other, "x@other.in", "Other")
    verify_email("x@other.in")
    d2 = other.post("/api/org/domains", json={"domain": "acme.in"}).json()
    assert other.post(f"/api/org/domains/{d2['id']}/verify").status_code == 409


def test_api_keys_are_hashed_and_scoped(owner, db):
    r = owner.post("/api/org/api-keys", json={"name": "Website", "scopes": ["consent:write"]}).json()
    assert r["secret"].startswith("prm_") and r["prefix"] == r["secret"][:12]
    listed = owner.get("/api/org/api-keys").json()["keys"]
    assert "secret" not in json.dumps(listed)
    from app.models import ApiKey

    stored = db.scalar(select(ApiKey))
    assert stored.key_hash != r["secret"] and r["secret"] not in json.dumps(stored.scopes)
    assert owner.delete(f"/api/org/api-keys/{r['id']}").status_code == 204


def test_metrics_endpoint(owner, monkeypatch):
    from app.config import get_settings

    c = make_client()
    c.post("/api/auth/login", json={"email": "owner@acme.in", "password": "Wrong-Password-123"})
    body = c.get("/metrics").text
    assert 'security_events_total{event="login_failed"}' in body and "http_requests_total" in body
    assert "owner@acme.in" not in body
    monkeypatch.setenv("METRICS_TOKEN", "s3cret")
    get_settings.cache_clear()
    try:
        assert c.get("/metrics").status_code == 404
        assert c.get("/metrics", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    finally:
        get_settings.cache_clear()
