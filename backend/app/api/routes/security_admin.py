"""Organisation security settings: MFA policy, session timeout, verified domains, SSO, API keys, audit chain."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.deps import DB, AdminCtx, Ctx
from app.models import ApiKey, Membership, OrgDomain, SsoConfig, User
from app.net_guard import UnsafeTargetError
from app.security import encrypt_str, hash_token
from app.services import audit, sso

router = APIRouter(prefix="/org", tags=["security"])

API_SCOPES = {
    "consent:write": "Record consent events from your website or app",
    "consent:read": "Read consent records",
    "scanner:write": "Upload findings from the self-hosted personal data scanner",
    "evidence:write": "Push check results from your own tools (CI, backup jobs, scripts) as evidence",
}


def _owner_only(ctx) -> None:
    if ctx.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owners can change this")


# ================================================================ policy


class SecurityPolicyIn(BaseModel):
    require_mfa: bool | None = None
    session_idle_minutes: int | None = Field(default=None, ge=5, le=24 * 60)


@router.get("/security")
def security_policy(db: DB, ctx: AdminCtx):
    rows = db.execute(select(User, Membership.role).join(Membership, Membership.user_id == User.id)
                      .where(Membership.org_id == ctx.org_id)).all()
    return {
        "require_mfa": ctx.org.require_mfa,
        "session_idle_minutes": ctx.org.session_idle_minutes,
        "members": [{"id": u.id, "full_name": u.full_name, "email": u.email, "role": role,
                     "mfa_enabled": u.mfa_enabled, "email_verified": u.email_verified_at is not None,
                     "last_login_at": u.last_login_at} for u, role in rows],
    }


@router.put("/security")
def update_security_policy(body: SecurityPolicyIn, db: DB, ctx: AdminCtx):
    org = ctx.org
    if body.require_mfa is not None and body.require_mfa != org.require_mfa:
        if body.require_mfa and not ctx.user.mfa_enabled:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Turn on multi-factor authentication for your own account first")
        org.require_mfa = body.require_mfa
    if body.session_idle_minutes is not None:
        org.session_idle_minutes = body.session_idle_minutes
    audit.record(db, ctx, "security.policy_updated", org, require_mfa=org.require_mfa,
                 session_idle_minutes=org.session_idle_minutes)
    db.commit()
    return security_policy(db, ctx)


# ================================================================ domains


class DomainIn(BaseModel):
    domain: str = Field(min_length=3, max_length=253)


def _domain_out(d: OrgDomain) -> dict:
    return {"id": d.id, "domain": d.domain, "verified_at": d.verified_at,
            "txt_record": f"{sso.DNS_PREFIX}{d.verification_token}"}


@router.get("/domains")
def list_domains(db: DB, ctx: AdminCtx):
    return [_domain_out(d) for d in db.scalars(select(OrgDomain).where(OrgDomain.org_id == ctx.org_id))]


@router.post("/domains", status_code=201)
def add_domain(body: DomainIn, db: DB, ctx: AdminCtx):
    domain = body.domain.strip().lower().removeprefix("@").rstrip(".")
    labels = domain.split(".")
    if len(labels) < 2 or not all(lbl and len(lbl) <= 63 and lbl.replace("-", "").isalnum() for lbl in labels):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a domain such as acme.in")
    if domain in sso.PUBLIC_EMAIL_DOMAINS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Public email domains can't be claimed")
    if db.scalar(select(OrgDomain).where(OrgDomain.org_id == ctx.org_id, OrgDomain.domain == domain)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You've already added this domain")
    d = OrgDomain(org_id=ctx.org_id, domain=domain, verification_token=secrets.token_hex(16))
    db.add(d)
    db.flush()
    audit.record(db, ctx, "security.domain_added", d, domain=domain)
    db.commit()
    return _domain_out(d)


@router.post("/domains/{domain_id}/verify")
def verify_domain(domain_id: uuid.UUID, db: DB, ctx: AdminCtx):
    d = db.get(OrgDomain, domain_id)
    if not d or d.org_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Domain not found")
    if d.verified_at:
        return _domain_out(d)
    from app.db import set_tenant

    set_tenant(db, rls_bypass=True)  # uniqueness check across organisations
    try:
        ok = sso.verify_domain(db, d)
    except sso.SsoError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    finally:
        set_tenant(db, rls_bypass=False)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"We couldn't find the TXT record on {d.domain} yet. DNS changes can take up to an hour.")
    audit.record(db, ctx, "security.domain_verified", d, domain=d.domain)
    db.commit()
    return _domain_out(d)


@router.delete("/domains/{domain_id}", status_code=204)
def remove_domain(domain_id: uuid.UUID, db: DB, ctx: AdminCtx):
    d = db.get(OrgDomain, domain_id)
    if not d or d.org_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Domain not found")
    audit.record(db, ctx, "security.domain_removed", d, domain=d.domain)
    db.delete(d)
    db.commit()


# ================================================================ SSO


class SsoIn(BaseModel):
    provider: str = Field(pattern="^(google|microsoft|okta|oidc)$")
    issuer: str = Field(default="", max_length=500, description="Tenant ID (Microsoft), Okta domain or issuer URL")
    client_id: str = Field(min_length=1, max_length=300)
    client_secret: str = Field(default="", max_length=500)
    enabled: bool = False
    enforced: bool = False
    jit_provisioning: bool = False
    default_role: str = Field(default="member", pattern="^(member|auditor)$")


def _sso_out(c: SsoConfig | None) -> dict:
    if not c:
        return {"configured": False, "redirect_uri": sso.redirect_uri()}
    return {"configured": True, "provider": c.provider, "issuer": c.issuer, "client_id": c.client_id,
            "client_secret_set": bool(c.client_secret_encrypted), "enabled": c.enabled, "enforced": c.enforced,
            "jit_provisioning": c.jit_provisioning, "default_role": c.default_role,
            "redirect_uri": sso.redirect_uri()}


@router.get("/sso")
def get_sso(db: DB, ctx: AdminCtx):
    return _sso_out(db.scalar(select(SsoConfig).where(SsoConfig.org_id == ctx.org_id)))


@router.put("/sso")
def put_sso(body: SsoIn, db: DB, ctx: AdminCtx):
    _owner_only(ctx)
    try:
        issuer = sso.issuer_for(body.provider, body.issuer)
    except (sso.SsoError, UnsafeTargetError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    cfg = db.scalar(select(SsoConfig).where(SsoConfig.org_id == ctx.org_id)) or SsoConfig(org_id=ctx.org_id)
    if body.enabled:
        if not db.scalar(select(OrgDomain.id).where(OrgDomain.org_id == ctx.org_id,
                                                    OrgDomain.verified_at.is_not(None)).limit(1)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verify at least one email domain before enabling SSO")
        if not (body.client_secret or cfg.client_secret_encrypted):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A client secret is required")
        try:
            sso.discovery(issuer)
        except (httpx.HTTPError, sso.SsoError, UnsafeTargetError, KeyError, ValueError) as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Couldn't read the provider's OpenID configuration from {issuer}") from e
    cfg.provider, cfg.issuer, cfg.client_id = body.provider, issuer, body.client_id.strip()
    if body.client_secret:
        cfg.client_secret_encrypted = encrypt_str(body.client_secret)
    cfg.enabled, cfg.enforced = body.enabled, body.enabled and body.enforced
    cfg.jit_provisioning, cfg.default_role = body.jit_provisioning, body.default_role
    db.add(cfg)
    db.flush()
    audit.record(db, ctx, "security.sso_updated", cfg, provider=cfg.provider, enabled=cfg.enabled,
                 enforced=cfg.enforced, jit=cfg.jit_provisioning)
    db.commit()
    return _sso_out(cfg)


# ================================================================ API keys


class ApiKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1)
    expires_in_days: int | None = Field(default=365, ge=1, le=730)


def _key_out(k: ApiKey) -> dict:
    return {"id": k.id, "name": k.name, "prefix": k.prefix, "scopes": k.scopes, "created_at": k.created_at,
            "last_used_at": k.last_used_at, "expires_at": k.expires_at, "revoked_at": k.revoked_at}


@router.get("/api-keys")
def list_api_keys(db: DB, ctx: AdminCtx):
    keys = db.scalars(select(ApiKey).where(ApiKey.org_id == ctx.org_id).order_by(ApiKey.created_at.desc()))
    return {"keys": [_key_out(k) for k in keys], "scopes": API_SCOPES}


@router.post("/api-keys", status_code=201)
def create_api_key(body: ApiKeyIn, db: DB, ctx: AdminCtx):
    unknown = set(body.scopes) - set(API_SCOPES)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown scopes: {sorted(unknown)}")
    secret = "prm_" + secrets.token_urlsafe(32)  # keys issued before the rename start with anp_ and still work
    k = ApiKey(org_id=ctx.org_id, name=body.name.strip(), prefix=secret[:12], key_hash=hash_token(secret),
               scopes=sorted(set(body.scopes)), created_by_id=ctx.user.id,
               expires_at=datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)
               if body.expires_in_days else None)
    db.add(k)
    db.flush()
    audit.record(db, ctx, "security.api_key_created", k, name=k.name, scopes=k.scopes)
    db.commit()
    return {**_key_out(k), "secret": secret}


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(key_id: uuid.UUID, db: DB, ctx: AdminCtx):
    k = db.get(ApiKey, key_id)
    if not k or k.org_id != ctx.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    k.revoked_at = k.revoked_at or datetime.now(timezone.utc)
    audit.record(db, ctx, "security.api_key_revoked", k, name=k.name)
    db.commit()


# ================================================================ audit chain


@router.get("/audit-log/verify")
def verify_audit_chain(db: DB, ctx: Ctx):
    if not (ctx.is_admin or ctx.role == "auditor"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin or auditor access required")
    return audit.verify_chain(db, ctx.org_id)
