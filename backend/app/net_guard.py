"""Outbound request guard (SSRF protection) for URLs and hosts supplied by customers."""
import ipaddress
import socket
from urllib.parse import urlparse

from app.config import get_settings


class UnsafeTargetError(ValueError):
    pass


def private_targets_allowed() -> bool:
    s = get_settings()
    return s.allow_private_scan_targets if s.allow_private_scan_targets is not None else not s.is_production


def check_host(host: str) -> None:
    """Refuse hosts that resolve to private, loopback, link-local or reserved addresses (in production)."""
    if not host:
        raise UnsafeTargetError("A host name is required")
    if private_targets_allowed():
        return
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(host, None)}
    except socket.gaierror as e:
        raise UnsafeTargetError(f"Can't resolve {host}") from e
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            raise UnsafeTargetError(f"{host} is on a private network and can't be reached from here")


def check_url(url: str, *, allowed_suffixes: tuple[str, ...] = ()) -> str:
    """Validate an https URL (optionally restricted to host suffixes) and return it normalised."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise UnsafeTargetError("Use an https:// URL")
    if parsed.username or parsed.password:
        raise UnsafeTargetError("URLs can't contain credentials")
    host = parsed.hostname.lower()
    if allowed_suffixes and not any(host == s.lstrip(".") or host.endswith(s if s.startswith(".") else f".{s}")
                                    for s in allowed_suffixes):
        raise UnsafeTargetError(f"Expected a host ending in {' or '.join(allowed_suffixes)}")
    check_host(host)
    return parsed._replace(fragment="").geturl().rstrip("/")


def check_hostname(value: str, *, allowed_suffixes: tuple[str, ...]) -> str:
    """Validate a bare host name such as acme.keka.com against allowed suffixes."""
    host = (value or "").strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
    if not host or "/" in host or ":" in host or "@" in host:
        raise UnsafeTargetError("Enter just the host name, e.g. acme.example.com")
    return urlparse(check_url(f"https://{host}", allowed_suffixes=allowed_suffixes)).hostname
