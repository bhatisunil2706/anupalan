import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, controls, dashboard, dpdp, frameworks, integrations, org, work
from app.config import get_settings
from app.db import SessionLocal

log = logging.getLogger("app")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.is_production:
        defaults = {"dev-only-insecure-secret-change-me", "q8B2o0p7ihyc7m0Kp0b2xH4bW8mE5Sgo3JpS5qYz2Xw="}
        if settings.secret_key in defaults or settings.encryption_key in defaults:
            raise RuntimeError("Set SECRET_KEY and ENCRYPTION_KEY before running in production")
        if not settings.cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true in production")
    if settings.load_content_on_startup:
        from app.services.content import load_content

        with SessionLocal() as db:
            log.info("content loaded: %s", load_content(db))
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/api/docs",
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def csrf_and_headers(request: Request, call_next):
        # Cookie-authenticated state changes must come from an allowed origin (defence in depth on top of SameSite).
        if request.method in UNSAFE_METHODS and settings.cookie_name in request.cookies:
            origin = request.headers.get("origin")
            if origin and origin not in settings.cors_origins:
                return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    for r in (auth, org, frameworks, controls, work, dpdp, integrations, dashboard):
        app.include_router(r.router, prefix="/api")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
