"""OpenID Connect single sign-on (Google Workspace, Microsoft Entra ID, Okta or any OIDC provider).

Security properties:
- An organisation can only use SSO for email domains it has proven it controls with a DNS TXT record, so one
  customer can't configure an identity provider that signs in another customer's users.
- Authorization code flow with PKCE (S256), a single-use `state`, and a `nonce` checked in the ID token.
- ID tokens are verified against the provider's published keys (asymmetric algorithms only), issuer, audience,
  expiry and nonce; the email must be verified by the provider and belong to one of the organisation's domains.
"""
import base64
import hashlib
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import dns.resolver
import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthToken, Membership, OrgDomain, SsoConfig, User
from app.net_guard import UnsafeTargetError, check_url  # noqa: F401 (re-exported for callers)
from app.security import decrypt_str, hash_token, new_token

log = logging.getLogger("sso")
STATE_MINUTES = 10
ALLOWED_ALGS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]
PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "yahoo.co.in",
    "icloud.com", "me.com", "proton.me", "protonmail.com", "rediffmail.com", "aol.com", "zoho.com", "gmx.com",
    "mail.com", "yandex.com",
}
DNS_PREFIX = "anupalan-verification="


class SsoError(Exception):
    pass


def issuer_for(provider: str, value: str) -> str:
    v = (value or "").strip().rstrip("/")
    if provider == "google":
        return "https://accounts.google.com"
    if provider == "microsoft":
        try:
            tenant = str(uuid.UUID(v))
        except ValueError as e:
            raise SsoError("Enter your Microsoft Entra directory (tenant) ID") from e
        return f"https://login.microsoftonline.com/{tenant}/v2.0"
    if provider == "okta":
        host = v.removeprefix("https://")
        return check_url(f"https://{host}", allowed_suffixes=("okta.com", "oktapreview.com", "okta-emea.com"))
    return check_url(v)


# ---------------------------------------------------------------- domains


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower().strip()


def verified_domain(db: Session, domain: str) -> OrgDomain | None:
    return db.scalar(select(OrgDomain).where(OrgDomain.domain == domain, OrgDomain.verified_at.is_not(None)))


def txt_records(domain: str) -> list[str]:
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 5
    try:
        answers = resolver.resolve(domain, "TXT")
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        return []
    return [b"".join(r.strings).decode(errors="replace") for r in answers]


def verify_domain(db: Session, d: OrgDomain) -> bool:
    if verified_domain(db, d.domain):
        raise SsoError("This domain is already verified by another organisation")
    if any(t.strip() == f"{DNS_PREFIX}{d.verification_token}" for t in txt_records(d.domain)):
        d.verified_at = datetime.now(timezone.utc)
        return True
    return False


def enforced_sso_org(db: Session, email: str) -> uuid.UUID | None:
    """Org whose enforced SSO covers this email's domain, if any."""
    d = verified_domain(db, email_domain(email))
    if not d:
        return None
    cfg = db.scalar(select(SsoConfig).where(SsoConfig.org_id == d.org_id))
    return d.org_id if cfg and cfg.enabled and cfg.enforced else None


def password_login_blocked(db: Session, user: User) -> bool:
    org_id = enforced_sso_org(db, user.email)
    if not org_id:
        return False
    m = db.scalar(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user.id))
    return not (m and m.role == "owner")  # owners keep password + MFA as break-glass access


# ---------------------------------------------------------------- discovery and keys

_discovery_cache: dict[str, tuple[float, dict]] = {}
_jwk_clients: dict[str, jwt.PyJWKClient] = {}


def discovery(issuer: str, client: httpx.Client | None = None) -> dict:
    cached = _discovery_cache.get(issuer)
    if cached and cached[0] > time.time():
        return cached[1]
    url = check_url(f"{issuer}/.well-known/openid-configuration")
    r = (client or httpx).get(url, timeout=10)
    r.raise_for_status()
    doc = r.json()
    if doc.get("issuer", "").rstrip("/") != issuer.rstrip("/"):
        raise SsoError("The provider's discovery document has a different issuer")
    for k in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        check_url(doc[k])
    _discovery_cache[issuer] = (time.time() + 3600, doc)
    return doc


def signing_key(jwks_uri: str, token: str):
    client = _jwk_clients.setdefault(jwks_uri, jwt.PyJWKClient(jwks_uri, cache_keys=True, lifespan=3600))
    return client.get_signing_key_from_jwt(token).key


# ---------------------------------------------------------------- flow


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}/api/auth/sso/callback"


def start(db: Session, email: str, client: httpx.Client | None = None) -> str:
    d = verified_domain(db, email_domain(email))
    cfg = db.scalar(select(SsoConfig).where(SsoConfig.org_id == d.org_id)) if d else None
    if not cfg or not cfg.enabled:
        raise SsoError("Single sign-on isn't set up for this email domain. Sign in with your password.")
    doc = discovery(cfg.issuer, client)
    state, state_hash = new_token()
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = _pkce()
    db.add(AuthToken(purpose="sso_state", token_hash=state_hash, org_id=cfg.org_id,
                     data={"nonce": nonce, "verifier": verifier, "email": email.lower()},
                     expires_at=datetime.now(timezone.utc) + timedelta(minutes=STATE_MINUTES)))
    params = {"client_id": cfg.client_id, "response_type": "code", "scope": "openid email profile",
              "redirect_uri": redirect_uri(), "state": state, "nonce": nonce, "code_challenge": challenge,
              "code_challenge_method": "S256", "login_hint": email, "prompt": "select_account"}
    return str(httpx.URL(doc["authorization_endpoint"], params=params))


def complete(db: Session, state: str, code: str, client: httpx.Client | None = None) -> tuple[User, uuid.UUID]:
    """Validate the callback. Returns (user, org_id) to sign in, provisioning the user/membership if allowed."""
    now = datetime.now(timezone.utc)
    tok = db.scalar(select(AuthToken).where(AuthToken.purpose == "sso_state",
                                            AuthToken.token_hash == hash_token(state or "")))
    if not tok or tok.used_at or tok.expires_at <= now:
        raise SsoError("This sign-in link has expired. Please try again.")
    tok.used_at = now
    cfg = db.scalar(select(SsoConfig).where(SsoConfig.org_id == tok.org_id))
    if not cfg or not cfg.enabled:
        raise SsoError("Single sign-on is no longer enabled for this organisation.")
    doc = discovery(cfg.issuer, client)
    r = (client or httpx).post(doc["token_endpoint"], timeout=15, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(),
        "client_id": cfg.client_id, "client_secret": decrypt_str(cfg.client_secret_encrypted),
        "code_verifier": tok.data["verifier"],
    })
    if r.status_code != 200:
        log.warning("sso token exchange failed: %s %s", r.status_code, r.text[:200])
        raise SsoError("The identity provider rejected the sign-in.")
    id_token = r.json().get("id_token")
    if not id_token:
        raise SsoError("The identity provider didn't return an ID token.")
    try:
        claims = jwt.decode(id_token, signing_key(doc["jwks_uri"], id_token), algorithms=ALLOWED_ALGS,
                            audience=cfg.client_id, issuer=cfg.issuer, leeway=60,
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.PyJWTError as e:
        raise SsoError(f"The ID token couldn't be verified ({e}).") from e
    if not secrets.compare_digest(str(claims.get("nonce", "")), tok.data["nonce"]):
        raise SsoError("The sign-in response didn't match this request.")

    email = (claims.get("email") or (claims.get("preferred_username") if cfg.provider == "microsoft" else "")
             or "").lower().strip()
    if not email or "@" not in email:
        raise SsoError("The identity provider didn't share an email address.")
    if claims.get("email_verified") is False or (cfg.provider == "google" and claims.get("email_verified") is not True):
        raise SsoError("Your email address isn't verified with the identity provider.")
    d = verified_domain(db, email_domain(email))
    if not d or d.org_id != cfg.org_id:
        raise SsoError("Your email domain isn't verified for this organisation.")

    user = db.scalar(select(User).where(User.email == email))
    membership = db.scalar(select(Membership).where(Membership.org_id == cfg.org_id,
                                                    Membership.user_id == user.id)) if user else None
    if membership and membership.expires_at and membership.expires_at <= now:
        raise SsoError("Your access to this organisation has expired.")
    if not membership and not cfg.jit_provisioning:
        raise SsoError("You don't have access yet. Ask an administrator to invite you.")
    if user is None:
        name = claims.get("name") or email.split("@")[0]
        user = User(email=email, full_name=str(name)[:200], password_hash="!sso-only", email_verified_at=now)
        db.add(user)
        db.flush()
    elif not user.is_active:
        raise SsoError("Your account is disabled.")
    if user.email_verified_at is None:
        user.email_verified_at = now
    if not membership:
        db.add(Membership(user_id=user.id, org_id=cfg.org_id, role=cfg.default_role))
    user.last_login_at = now
    return user, cfg.org_id
