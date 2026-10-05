"""Cryptographic helpers: password hashing and policy, tokens, encryption, TOTP and recovery codes."""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time

import httpx
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken
from zxcvbn import zxcvbn

from app.config import get_settings

log = logging.getLogger("security")
_hasher = PasswordHasher()  # Argon2id, RFC 9106 low-memory profile defaults

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 200
# A hash of a random password, used to keep sign-in timing the same whether or not the account exists.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


class WeakPasswordError(ValueError):
    pass


def breached_count(password: str) -> int:
    """Times the password appears in Have I Been Pwned. Only the first 5 hex chars of its SHA-1 are sent."""
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        r = httpx.get(f"https://api.pwnedpasswords.com/range/{prefix}", timeout=3,
                      headers={"Add-Padding": "true", "User-Agent": "anupalan-password-check"})
        r.raise_for_status()
    except httpx.HTTPError:
        log.warning("breached password check unavailable; continuing without it")
        return 0
    for line in r.text.splitlines():
        h, _, n = line.partition(":")
        if h == suffix:
            return int(n or 0)
    return 0


def check_password_strength(password: str, user_inputs: list[str] | None = None) -> None:
    """Raise WeakPasswordError with a helpful message if the password is too weak."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    base = [i for i in (user_inputs or []) if i]
    inputs = base + [p for i in base for p in i.replace("@", " ").replace(".", " ").split() if len(p) >= 3]
    squashed = "".join(ch for ch in password.lower() if ch.isalnum())
    personal = [p.lower() for p in inputs if len(p) >= 4]
    if any("".join(ch for ch in p if ch.isalnum()) in squashed for p in personal):
        raise WeakPasswordError("Don't include your name, email or company name.")
    result = zxcvbn(password[:100], user_inputs=inputs)
    if result["score"] < 3:
        hint = result["feedback"].get("warning") or "It's too easy to guess."
        raise WeakPasswordError(f"{hint} Try a longer passphrase of several unrelated words.")
    if get_settings().breach_check_enabled and breached_count(password):
        raise WeakPasswordError("This password has appeared in a data breach. Choose a different one.")


# ---------------------------------------------------------------- tokens


def new_token(nbytes: int = 32) -> tuple[str, str]:
    """Return (plain token, sha256 hash). Store only the hash."""
    token = secrets.token_urlsafe(nbytes)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def keyed_hash(value: str) -> str:
    """HMAC with the server secret, for short secrets such as recovery codes."""
    return hmac.new(get_settings().secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def safe_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ---------------------------------------------------------------- encryption


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except InvalidToken:
        log.error("could not decrypt stored secret (wrong ENCRYPTION_KEY?)")
        return {}


def encrypt_str(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_str(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode() if token else ""


# ---------------------------------------------------------------- TOTP (RFC 6238) and recovery codes

TOTP_INTERVAL = 30


def new_totp_secret() -> str:
    return pyotp.random_base32(32)  # 160 bits


def totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=get_settings().app_name)


def verify_totp(secret: str, code: str, last_timestep: int, now: float | None = None) -> int | None:
    """Return the matched timestep if the code is valid and newer than the last one used, else None.

    Accepts one step of clock drift either way. Rejecting steps <= last_timestep blocks replay.
    """
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != 6 or not secret:
        return None
    now = time.time() if now is None else now
    totp = pyotp.TOTP(secret)
    current = int(now // TOTP_INTERVAL)
    for step in (current, current - 1, current + 1):
        if step > last_timestep and hmac.compare_digest(totp.at(step * TOTP_INTERVAL), code):
            return step
    return None


def new_recovery_codes(n: int = 10) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
    codes = []
    for _ in range(n):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalise_recovery_code(code: str) -> str:
    c = "".join(ch for ch in code.upper() if ch.isalnum())
    return f"{c[:5]}-{c[5:]}" if len(c) == 10 else c


def qr_svg_data_uri(data: str) -> str:
    import io

    import segno

    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=5, border=2, dark="#171b2e", light="#ffffff")
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
