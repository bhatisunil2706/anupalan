import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import ratelimit
from app.api.routes import (
    auth,
    automation,
    controls,
    dashboard,
    dpdp,
    frameworks,
    integrations,
    org,
    portal,
    security_admin,
    work,
)
from app.config import get_settings
from app.db import engine, system_session
from app.request_context import client_ip, request_id, user_agent

log = logging.getLogger("app")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Endpoints that don't act on behalf of an existing session (or are protected by their own token), so they
# don't need the CSRF header. The Origin check still applies.
CSRF_EXEMPT = {
    "/api/auth/login", "/api/auth/signup", "/api/auth/logout", "/api/auth/mfa/verify", "/api/auth/password/forgot",
    "/api/auth/password/reset", "/api/auth/email/verify", "/api/auth/sso/start", "/api/auth/invitations/accept",
}
JSON_BODY_LIMIT = 2 * 1024 * 1024


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
                 "logger": record.name, "msg": record.getMessage(), "request_id": request_id.get()}
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging() -> None:
    s = get_settings()
    handler = logging.StreamHandler()
    if s.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)


def startup_checks() -> None:
    from app.rls import runtime_role_report

    s = get_settings()
    problems = []
    if s.is_production:
        defaults = {"dev-only-insecure-secret-change-me", "q8B2o0p7ihyc7m0Kp0b2xH4bW8mE5Sgo3JpS5qYz2Xw="}
        if s.secret_key in defaults or len(s.secret_key) < 32:
            problems.append("SECRET_KEY must be a random value of at least 32 characters")
        if s.encryption_key in defaults:
            problems.append("ENCRYPTION_KEY must be set to a new Fernet key")
        if not s.cookie_secure:
            problems.append("COOKIE_SECURE must be true (serve the app over HTTPS)")
        if not s.redis_url:
            problems.append("REDIS_URL is required so rate limits and lockouts work across instances")
        if not s.public_url.startswith("https://"):
            problems.append("PUBLIC_URL must be https://")
    with engine.connect() as conn:
        report = runtime_role_report(conn)
    if report["superuser"] or report["bypassrls"] or not report["rls_forced"]:
        msg = (f"database role '{report['role']}' bypasses row-level security (superuser={report['superuser']}, "
               f"bypassrls={report['bypassrls']}, rls_forced={report['rls_forced']})")
        if s.is_production:
            problems.append(msg + "; connect with the restricted runtime role")
        else:
            log.warning("%s. Fine for local development, never in production.", msg)
    if problems:
        raise RuntimeError("Refusing to start: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    if settings.environment != "test":
        startup_checks()
    if settings.load_content_on_startup:
        from app.services.content import load_content

        with system_session() as db:
            log.info("content loaded: %s", load_content(db))
    yield


def _origin_allowed(request: Request, allowed: list[str]) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if not referer:
            return True  # non-browser client; browsers always send Origin on cross-site POSTs
        p = urlparse(referer)
        origin = f"{p.scheme}://{p.netloc}"
    return origin in allowed


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.3.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/api/docs",
        openapi_url=None if settings.is_production else "/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"],
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex
        tokens = (request_id.set(rid), client_ip.set(request.client.host if request.client else ""),
                  user_agent.set(request.headers.get("user-agent", "")[:300]))
        try:
            path = request.url.path
            # Request size limits (evidence uploads are capped again while reading).
            length = request.headers.get("content-length")
            limit = (settings.max_upload_mb + 1) * 1024 * 1024 if "multipart" in request.headers.get(
                "content-type", "") else JSON_BODY_LIMIT
            if length and length.isdigit() and int(length) > limit:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            if path.startswith("/api/") and ratelimit.hit("global-ip", client_ip.get(), 900, 60):
                return JSONResponse({"detail": "Too many requests"}, status_code=429)
            if request.method in UNSAFE_METHODS:
                if not _origin_allowed(request, settings.cors_origins):
                    return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
                session_cookie = request.cookies.get(settings.cookie_name)
                if session_cookie and path not in CSRF_EXEMPT:
                    expected = request.cookies.get(settings.csrf_cookie_name, "")
                    sent = request.headers.get("x-csrf-token", "")
                    if not expected or not secrets.compare_digest(expected, sent):
                        return JSONResponse({"detail": "Security check failed. Refresh the page and try again."},
                                            status_code=403)
            started = time.monotonic()
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            h = response.headers
            h.setdefault("X-Content-Type-Options", "nosniff")
            h.setdefault("X-Frame-Options", "DENY")
            h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
            h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
            h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            if path.startswith("/api/") and not path.startswith("/api/docs"):
                h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                h.setdefault("Cache-Control", "no-store")
            if settings.cookie_secure:
                h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
            if time.monotonic() - started > 5:
                log.warning("slow request %s %s", request.method, path)
            return response
        finally:
            for var, tok in zip((request_id, client_ip, user_agent), tokens, strict=True):
                var.reset(tok)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Something went wrong on our side.", "request_id": request_id.get()},
                            status_code=500)

    for r in (auth, org, security_admin, frameworks, controls, work, dpdp, integrations, dashboard, automation,
              portal):
        app.include_router(r.router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/ready")
    def ready():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ratelimit.count("ready", "probe")
        return {"status": "ready"}

    return app


app = create_app()
