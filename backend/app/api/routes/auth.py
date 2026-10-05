"""Sign-up, sign-in (password, MFA, SSO), sessions, password and MFA management, invitations."""
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app import metrics, ratelimit
from app.config import get_settings
from app.db import set_tenant
from app.deps import (
    DB,
    CurrentSession,
    CurrentUser,
    active_membership,
    get_mfa_pending_session,
    mfa_satisfied,
)
from app.models import (
    AuthToken,
    Invitation,
    Membership,
    Organization,
    Policy,
    RecoveryCode,
    User,
    UserSession,
)
from app.request_context import client_ip, user_agent
from app.schemas import (
    AcceptInviteIn,
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    MembershipOut,
    MeOut,
    MfaCodeIn,
    PasswordConfirmIn,
    ResetPasswordIn,
    SignupIn,
    SwitchOrgIn,
    TokenIn,
    UserBrief,
)
from app.security import (
    WeakPasswordError,
    check_password_strength,
    decrypt_str,
    encrypt_str,
    hash_password,
    hash_token,
    keyed_hash,
    new_recovery_codes,
    new_token,
    new_totp_secret,
    normalise_recovery_code,
    password_needs_rehash,
    qr_svg_data_uri,
    totp_uri,
    verify_password,
    verify_totp,
)
from app.services import audit, notify, sessions, sso

router = APIRouter(prefix="/auth", tags=["auth"])

LOCK_THRESHOLD, LOCK_WINDOW = 10, 60 * 60  # failed sign-ins per account per hour before a temporary lock
MAX_MFA_ATTEMPTS = 5
RESET_MINUTES = 30
VERIFY_HOURS = 48


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _strong_password(password: str, *inputs: str) -> None:
    try:
        check_password_strength(password, list(inputs))
    except WeakPasswordError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Password too weak. {e}") from e


def _me(db, user: User, sess: UserSession | None) -> MeOut:
    set_tenant(db, user_id=user.id)
    memberships = [m for m in db.scalars(select(Membership).where(Membership.user_id == user.id))
                   if not (m.expires_at and m.expires_at <= _now())]
    org_id = sess.org_id if sess else None
    current = next((m for m in memberships if m.org_id == org_id), None)
    return MeOut(
        user=UserBrief.model_validate(user),
        org_id=current.org_id if current else None,
        role=current.role if current else None,
        memberships=[MembershipOut(org_id=m.org_id, org_name=m.organization.name, role=m.role) for m in memberships],
        onboarded=bool(current and current.organization.onboarded_at),
        email_verified=user.email_verified_at is not None,
        mfa_enabled=user.mfa_enabled,
        mfa_setup_required=bool(current and sess and not mfa_satisfied(current.organization, user, sess)),
        auth_method=sess.auth_method if sess else "password",
        access_expires_at=current.expires_at if current else None,
    )


def _send(background: BackgroundTasks, to: str, subject: str, body: str) -> None:
    background.add_task(notify.send_email_safely, [to], subject, body)


def _issue_email_verification(db, user: User, background: BackgroundTasks) -> None:
    token, token_hash = new_token()
    db.add(AuthToken(purpose="email_verify", token_hash=token_hash, user_id=user.id,
                     expires_at=_now() + timedelta(hours=VERIFY_HOURS)))
    link = f"{get_settings().public_url.rstrip('/')}/verify-email?token={token}"
    _send(background, user.email, f"Confirm your email for {get_settings().app_name}",
          f"Hello {user.full_name},\n\nConfirm your email address by opening this link within {VERIFY_HOURS} "
          f"hours:\n\n{link}\n\nIf you didn't create an account, you can ignore this email.")


def _first_org(db, user_id: uuid.UUID) -> uuid.UUID | None:
    set_tenant(db, user_id=user_id)
    for m in db.scalars(select(Membership).where(Membership.user_id == user_id).order_by(Membership.created_at)):
        if not (m.expires_at and m.expires_at <= _now()):
            return m.org_id
    return None


def _alert_new_device(db, user: User, background: BackgroundTasks) -> None:
    ip, ua = client_ip.get(), user_agent.get()
    if not sessions.seen_before(db, user.id, ip, ua):
        _send(background, user.email, f"New sign-in to your {get_settings().app_name} account",
              f"Your account was just used to sign in from a new device or network.\n\nIP address: {ip or 'unknown'}"
              f"\nBrowser: {ua or 'unknown'}\nTime (UTC): {_now():%Y-%m-%d %H:%M}\n\nIf this was you, no action is "
              "needed. If not, reset your password now and review your active sessions in Account security.")


# ================================================================ sign-up and sign-in


@router.post("/signup", response_model=MeOut, status_code=201)
def signup(body: SignupIn, response: Response, background: BackgroundTasks, db: DB):
    ratelimit.enforce("signup-ip", client_ip.get(), 10, 3600)
    email = body.email.lower()
    _strong_password(body.password, email, body.full_name, body.org_name)
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(id=uuid.uuid4(), email=email, full_name=body.full_name.strip(),
                password_hash=hash_password(body.password), password_changed_at=_now())
    org = Organization(id=uuid.uuid4(), name=body.org_name.strip())
    set_tenant(db, org_id=org.id, user_id=user.id)
    db.add(user)
    db.flush()
    db.add(org)
    db.flush()
    db.add(Membership(user_id=user.id, org_id=org.id, role="owner"))
    audit.write(db, org_id=org.id, user_id=user.id, action="org.created", entity=org, detail={"by": email})
    _issue_email_verification(db, user, background)
    sess = sessions.create_session(db, response, user_id=user.id, org_id=org.id)
    db.commit()
    return _me(db, user, sess)


class LoginOut(BaseModel):
    mfa_required: bool = False
    me: MeOut | None = None


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, response: Response, background: BackgroundTasks, db: DB):
    email = body.email.lower()
    ip = client_ip.get()
    ratelimit.enforce("login-ip", ip, 50, 15 * 60, "Too many sign-in attempts from your network. Try again later.")
    if ratelimit.count("login-fail-acct", email) >= LOCK_THRESHOLD:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many failed attempts for this account. Try again in an hour or reset your password.")
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash if user else None):
        failures = ratelimit.increment("login-fail-acct", email, LOCK_WINDOW)
        metrics.event("login_failed")
        if failures == LOCK_THRESHOLD:
            metrics.event("account_locked")
        audit.write(db, org_id=None, user_id=user.id if user else None, action="auth.login_failed",
                    detail={"email": email})
        db.commit()
        if user and failures == LOCK_THRESHOLD:
            _send(background, user.email, "Your account was temporarily locked",
                  f"There were {LOCK_THRESHOLD} failed sign-in attempts on your account in the last hour, so "
                  "sign-in is paused for up to an hour. If this wasn't you, reset your password.")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    set_tenant(db, rls_bypass=True)  # domain ownership is checked across organisations
    blocked = sso.password_login_blocked(db, user)
    set_tenant(db, rls_bypass=False)
    if blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Your organisation requires single sign-on. Use 'Sign in with SSO'.")
    ratelimit.reset("login-fail-acct", email)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    org_id = _first_org(db, user.id)
    if user.mfa_enabled:
        sessions.create_session(db, response, user_id=user.id, org_id=org_id, stage="mfa")
        db.commit()
        return LoginOut(mfa_required=True)
    _alert_new_device(db, user, background)
    sess = sessions.create_session(db, response, user_id=user.id, org_id=org_id)
    user.last_login_at = _now()
    audit.write(db, org_id=org_id, user_id=user.id, action="auth.login", detail={"method": "password"})
    db.commit()
    return LoginOut(me=_me(db, user, sess))


@router.post("/mfa/verify", response_model=LoginOut)
def mfa_verify(body: MfaCodeIn, request: Request, response: Response, background: BackgroundTasks, db: DB,
               pending: UserSession = Depends(get_mfa_pending_session)):
    user = db.get(User, pending.user_id)
    pending.mfa_attempts += 1
    if pending.mfa_attempts > MAX_MFA_ATTEMPTS:
        sessions.revoke(db, pending)
        db.commit()
        sessions.clear_cookies(response)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many incorrect codes. Please sign in again.")
    method = _check_second_factor(db, user, body.code)
    if not method:
        audit.write(db, org_id=None, user_id=user.id, action="auth.mfa_failed")
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code didn't work. Try again.")
    # Rotate: the challenge session ends and a fresh full session (new token) starts.
    sessions.revoke(db, pending)
    _alert_new_device(db, user, background)
    sess = sessions.create_session(db, response, user_id=user.id, org_id=pending.org_id, mfa_verified=True)
    user.last_login_at = _now()
    audit.write(db, org_id=pending.org_id, user_id=user.id, action="auth.login",
                detail={"method": "password", "mfa": method})
    db.commit()
    return LoginOut(me=_me(db, user, sess))


def _check_second_factor(db, user: User, code: str) -> str | None:
    """Verify a TOTP code or an unused recovery code. Returns "totp", "recovery_code" or None."""
    step = verify_totp(decrypt_str(user.mfa_secret_encrypted), code, user.mfa_last_timestep)
    if step is not None:
        user.mfa_last_timestep = step
        return "totp"
    rc = db.scalar(select(RecoveryCode).where(RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None),
                                              RecoveryCode.code_hash == keyed_hash(normalise_recovery_code(code))))
    if rc:
        rc.used_at = _now()
        return "recovery_code"
    return None


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB):
    sess = sessions.lookup(db, sessions.token_from_request(request))
    if sess:
        sessions.revoke(db, sess)
        db.commit()
    sessions.clear_cookies(response)


@router.get("/me", response_model=MeOut)
def me(db: DB, user: CurrentUser, sess: CurrentSession):
    return _me(db, user, sess)


@router.post("/switch-org", response_model=MeOut)
def switch_org(body: SwitchOrgIn, db: DB, user: CurrentUser, sess: CurrentSession):
    if not active_membership(db, user.id, body.org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this organisation")
    sess.org_id = body.org_id
    db.commit()
    return _me(db, user, sess)


# ================================================================ SSO


class SsoStartIn(BaseModel):
    email: EmailStr


@router.post("/sso/start")
def sso_start(body: SsoStartIn, db: DB):
    ratelimit.enforce("sso-start", client_ip.get(), 30, 15 * 60)
    set_tenant(db, rls_bypass=True)  # find the organisation that owns this verified domain
    try:
        url = sso.start(db, body.email)
    except sso.SsoError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    db.commit()
    return {"redirect_url": url}


@router.get("/sso/callback")
def sso_callback(db: DB, background: BackgroundTasks, state: str = "", code: str = "", error: str = ""):
    if error or not code:
        return RedirectResponse("/login?sso_error=cancelled", status_code=303)
    set_tenant(db, rls_bypass=True)
    try:
        user, org_id = sso.complete(db, state, code)
    except (sso.SsoError, sso.UnsafeTargetError, httpx.HTTPError) as e:
        db.commit()  # keep the state token marked as used
        msg = str(e) if isinstance(e, sso.SsoError) else "We couldn't reach your identity provider."
        return RedirectResponse(f"/login?sso_error={quote(msg)}", status_code=303)
    set_tenant(db, rls_bypass=False, org_id=org_id, user_id=user.id)
    redirect = RedirectResponse("/dashboard", status_code=303)
    _alert_new_device(db, user, background)
    sessions.create_session(db, redirect, user_id=user.id, org_id=org_id, auth_method="sso")
    audit.write(db, org_id=org_id, user_id=user.id, action="auth.login", detail={"method": "sso"})
    db.commit()
    return redirect


# ================================================================ email verification


@router.post("/email/verify")
def verify_email(body: TokenIn, db: DB):
    tok = db.scalar(select(AuthToken).where(AuthToken.purpose == "email_verify",
                                            AuthToken.token_hash == hash_token(body.token)))
    if not tok or tok.used_at or tok.expires_at <= _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This link is invalid or has expired")
    tok.used_at = _now()
    user = db.get(User, tok.user_id)
    user.email_verified_at = user.email_verified_at or _now()
    db.commit()
    return {"verified": True, "email": user.email}


@router.post("/email/resend", status_code=202)
def resend_verification(background: BackgroundTasks, db: DB, user: CurrentUser):
    ratelimit.enforce("verify-resend", str(user.id), 5, 3600)
    if not user.email_verified_at:
        _issue_email_verification(db, user, background)
        db.commit()
    return {"status": "sent"}


# ================================================================ passwords


@router.post("/password/forgot", status_code=202)
def forgot_password(body: ForgotPasswordIn, background: BackgroundTasks, db: DB):
    email = body.email.lower()
    ratelimit.enforce("forgot-ip", client_ip.get(), 10, 3600)
    if ratelimit.hit("forgot-email", email, 3, 3600):
        return {"status": "sent"}  # same answer either way, so this can't be used to find accounts
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user and user.is_active:
        token, token_hash = new_token()
        db.add(AuthToken(purpose="password_reset", token_hash=token_hash, user_id=user.id,
                         expires_at=_now() + timedelta(minutes=RESET_MINUTES)))
        db.commit()
        link = f"{get_settings().public_url.rstrip('/')}/reset-password?token={token}"
        _send(background, user.email, f"Reset your {get_settings().app_name} password",
              f"Someone asked to reset the password for {user.email}. Open this link within {RESET_MINUTES} minutes "
              f"to choose a new one:\n\n{link}\n\nIf this wasn't you, ignore this email; your password won't "
              "change. Multi-factor authentication is still required after a reset.")
    return {"status": "sent"}


@router.post("/password/reset")
def reset_password(body: ResetPasswordIn, background: BackgroundTasks, db: DB):
    ratelimit.enforce("reset-ip", client_ip.get(), 20, 3600)
    tok = db.scalar(select(AuthToken).where(AuthToken.purpose == "password_reset",
                                            AuthToken.token_hash == hash_token(body.token)))
    if not tok or tok.used_at or tok.expires_at <= _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired")
    user = db.get(User, tok.user_id)
    _strong_password(body.password, user.email, user.full_name)
    tok.used_at = _now()
    user.password_hash = hash_password(body.password)
    user.password_changed_at = _now()
    user.email_verified_at = user.email_verified_at or _now()  # the link proved control of the inbox
    revoked = sessions.revoke_all(db, user.id)
    ratelimit.reset("login-fail-acct", user.email)
    audit.write(db, org_id=None, user_id=user.id, action="auth.password_reset", detail={"sessions_revoked": revoked})
    db.commit()
    _send(background, user.email, "Your password was changed",
          "Your password was just reset and all your sessions were signed out. If this wasn't you, contact your "
          "administrator immediately.")
    return {"status": "reset"}


@router.post("/password/change", status_code=204)
def change_password(body: ChangePasswordIn, background: BackgroundTasks, db: DB, user: CurrentUser,
                    sess: CurrentSession):
    ratelimit.enforce("pw-change", str(user.id), 10, 3600)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is incorrect")
    _strong_password(body.new_password, user.email, user.full_name)
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = _now()
    revoked = sessions.revoke_all(db, user.id, except_id=sess.id)
    audit.write(db, org_id=sess.org_id, user_id=user.id, action="auth.password_changed",
                detail={"other_sessions_revoked": revoked})
    db.commit()
    _send(background, user.email, "Your password was changed",
          "Your password was changed and your other sessions were signed out. If this wasn't you, reset your "
          "password and contact your administrator.")


# ================================================================ MFA management


def _confirm(db, user: User, body: PasswordConfirmIn, require_code: bool) -> None:
    ratelimit.enforce("confirm", str(user.id), 10, 15 * 60)
    if user.password_hash.startswith("!sso"):
        if not (require_code and _check_second_factor(db, user, body.code)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter a current authentication code")
        return
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your password is incorrect")
    if require_code and not _check_second_factor(db, user, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That authentication code didn't work")


def _store_recovery_codes(db, user: User) -> list[str]:
    for rc in db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user.id)):
        db.delete(rc)
    codes = new_recovery_codes()
    for c in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=keyed_hash(c)))
    return codes


@router.post("/mfa/setup")
def mfa_setup(db: DB, user: CurrentUser):
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Multi-factor authentication is already on")
    secret = new_totp_secret()
    _, token_hash = new_token()
    for old in db.scalars(select(AuthToken).where(AuthToken.purpose == "mfa_setup", AuthToken.user_id == user.id,
                                                  AuthToken.used_at.is_(None))):
        old.used_at = _now()
    db.add(AuthToken(purpose="mfa_setup", token_hash=token_hash, user_id=user.id,
                     data={"secret": encrypt_str(secret)}, expires_at=_now() + timedelta(minutes=15)))
    db.commit()
    uri = totp_uri(secret, user.email)
    return {"secret": secret, "otpauth_uri": uri, "qr": qr_svg_data_uri(uri)}


@router.post("/mfa/enable")
def mfa_enable(body: MfaCodeIn, background: BackgroundTasks, db: DB, user: CurrentUser, sess: CurrentSession):
    ratelimit.enforce("mfa-enable", str(user.id), 10, 15 * 60)
    pending = db.scalar(select(AuthToken).where(AuthToken.purpose == "mfa_setup", AuthToken.user_id == user.id,
                                                AuthToken.used_at.is_(None), AuthToken.expires_at > _now())
                        .order_by(AuthToken.created_at.desc()))
    if not pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Start setup again; the setup code expired")
    secret = decrypt_str(pending.data["secret"])
    step = verify_totp(secret, body.code, 0)
    if step is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "That code didn't match. Check your phone's clock and try again.")
    pending.used_at = _now()
    user.mfa_secret_encrypted = encrypt_str(secret)
    user.mfa_last_timestep = step
    user.mfa_enabled, user.mfa_enabled_at = True, _now()
    sess.mfa_verified = True
    codes = _store_recovery_codes(db, user)
    revoked = sessions.revoke_all(db, user.id, except_id=sess.id)
    audit.write(db, org_id=sess.org_id, user_id=user.id, action="auth.mfa_enabled",
                detail={"other_sessions_revoked": revoked})
    db.commit()
    _send(background, user.email, "Multi-factor authentication turned on",
          "Multi-factor authentication is now on for your account. Keep your recovery codes somewhere safe.")
    return {"recovery_codes": codes}


@router.post("/mfa/disable", status_code=204)
def mfa_disable(body: PasswordConfirmIn, background: BackgroundTasks, db: DB, user: CurrentUser,
                sess: CurrentSession):
    if not user.mfa_enabled:
        return
    _confirm(db, user, body, require_code=True)
    set_tenant(db, user_id=user.id)
    requiring = [m.organization.name for m in db.scalars(select(Membership).where(Membership.user_id == user.id))
                 if m.organization.require_mfa]
    if requiring:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"{', '.join(requiring)} requires multi-factor authentication, so it can't be turned off.")
    user.mfa_enabled, user.mfa_secret_encrypted, user.mfa_last_timestep = False, "", 0
    for rc in db.scalars(select(RecoveryCode).where(RecoveryCode.user_id == user.id)):
        db.delete(rc)
    audit.write(db, org_id=sess.org_id, user_id=user.id, action="auth.mfa_disabled")
    db.commit()
    _send(background, user.email, "Multi-factor authentication turned off",
          "Multi-factor authentication was turned off for your account. If this wasn't you, reset your password "
          "and turn it back on.")


@router.post("/mfa/recovery-codes")
def regenerate_recovery_codes(body: PasswordConfirmIn, db: DB, user: CurrentUser, sess: CurrentSession):
    if not user.mfa_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Turn on multi-factor authentication first")
    _confirm(db, user, body, require_code=True)
    codes = _store_recovery_codes(db, user)
    audit.write(db, org_id=sess.org_id, user_id=user.id, action="auth.recovery_codes_regenerated")
    db.commit()
    return {"recovery_codes": codes}


@router.get("/mfa/status")
def mfa_status(db: DB, user: CurrentUser):
    remaining = db.scalar(select(func.count()).select_from(RecoveryCode).where(
        RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None))) if user.mfa_enabled else 0
    return {"enabled": user.mfa_enabled, "enabled_at": user.mfa_enabled_at, "recovery_codes_remaining": remaining,
            "password_changed_at": user.password_changed_at, "sso_only": user.password_hash.startswith("!sso")}


# ================================================================ sessions


@router.get("/sessions")
def list_sessions(db: DB, user: CurrentUser, sess: CurrentSession):
    return [{"id": s.id, "current": s.id == sess.id, "ip": s.ip, "user_agent": s.user_agent,
             "auth_method": s.auth_method, "created_at": s.created_at, "last_seen_at": s.last_seen_at}
            for s in sessions.active_sessions(db, user.id)]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: uuid.UUID, response: Response, db: DB, user: CurrentUser, sess: CurrentSession):
    target = db.get(UserSession, session_id)
    if not target or target.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    sessions.revoke(db, target)
    audit.write(db, org_id=sess.org_id, user_id=user.id, action="auth.session_revoked",
                detail={"session": str(session_id)})
    db.commit()
    if target.id == sess.id:
        sessions.clear_cookies(response)


@router.post("/sessions/revoke-others")
def revoke_other_sessions(db: DB, user: CurrentUser, sess: CurrentSession):
    n = sessions.revoke_all(db, user.id, except_id=sess.id)
    audit.write(db, org_id=sess.org_id, user_id=user.id, action="auth.sessions_revoked", detail={"count": n})
    db.commit()
    return {"revoked": n}


# ================================================================ invitations


def _valid_invitation(db, token: str) -> Invitation:
    set_tenant(db, rls_bypass=True)  # the token is the credential; look it up across organisations
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    set_tenant(db, rls_bypass=False)
    if not inv or inv.accepted_at or inv.expires_at < _now():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invitation is invalid or has expired")
    set_tenant(db, org_id=inv.org_id)
    return inv


@router.get("/invitations/{token}")
def invitation_info(token: str, db: DB):
    ratelimit.enforce("invite-lookup", client_ip.get(), 30, 15 * 60)
    inv = _valid_invitation(db, token)
    org = db.get(Organization, inv.org_id)
    existing = db.scalar(select(User.id).where(func.lower(User.email) == inv.email.lower()))
    return {"email": inv.email, "org_name": org.name, "role": inv.role, "has_account": bool(existing),
            "access_expires_at": inv.access_expires_at}


@router.post("/invitations/accept", response_model=MeOut)
def accept_invitation(body: AcceptInviteIn, request: Request, response: Response, db: DB):
    ratelimit.enforce("invite-accept", client_ip.get(), 20, 15 * 60)
    inv = _valid_invitation(db, body.token)
    user = db.scalar(select(User).where(func.lower(User.email) == inv.email.lower()))
    sess = None
    if user is None:
        if not body.full_name or not body.password:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name and password are required to create your account")
        _strong_password(body.password, inv.email, body.full_name)
        user = User(email=inv.email.lower(), full_name=body.full_name.strip(),
                    password_hash=hash_password(body.password), password_changed_at=_now(),
                    email_verified_at=_now())  # the invitation link proved control of the inbox
        db.add(user)
        db.flush()
    else:
        sess = sessions.lookup(db, sessions.token_from_request(request))
        if not sess or sess.stage != "full" or sess.user_id != user.id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in with the invited email to accept")
    set_tenant(db, user_id=user.id)
    if not db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.org_id == inv.org_id)):
        db.add(Membership(user_id=user.id, org_id=inv.org_id, role=inv.role, expires_at=inv.access_expires_at))
        approved = db.scalar(select(func.count()).select_from(Policy).where(
            Policy.org_id == inv.org_id, Policy.status == "approved"))
        if approved and inv.role != "auditor":
            notify.queue(db, inv.org_id, key=f"welcome:{user.id}", event="policy_approved", to=[user.email],
                         title=f"Welcome! Please read and acknowledge {approved} company policies",
                         link="/policies")
    inv.accepted_at = _now()
    audit.write(db, org_id=inv.org_id, user_id=user.id, action="member.joined", detail={"role": inv.role})
    if sess is None:
        sess = sessions.create_session(db, response, user_id=user.id, org_id=inv.org_id)
    else:
        sess.org_id = inv.org_id
    db.commit()
    return _me(db, user, sess)
