from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Pramaanly"
    environment: str = "development"  # development | test | production

    database_url: str = "postgresql+psycopg://postgres@localhost:5432/app"

    # Secrets. MUST be overridden in production (startup refuses the defaults outside development).
    secret_key: str = "dev-only-insecure-secret-change-me"
    # Fernet key (32 url-safe base64 bytes) used to encrypt integration credentials at rest.
    encryption_key: str = "q8B2o0p7ihyc7m0Kp0b2xH4bW8mE5Sgo3JpS5qYz2Xw="

    # Sessions are server-side and revocable. Absolute lifetime; idle timeout is set per organisation.
    session_absolute_hours: int = 12
    mfa_challenge_minutes: int = 10
    cookie_secure: bool = False  # set True behind HTTPS (required in production)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    storage_dir: Path = Path("./storage")
    max_upload_mb: int = 25

    load_content_on_startup: bool = True

    # Public URL of the web app, used in emails and notification links.
    public_url: str = "http://localhost:3000"

    # Outgoing email (SMTP). If smtp_host is empty, emails are logged instead of sent.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Pramaanly <no-reply@localhost>"
    smtp_starttls: bool = True

    # Personal data scanner: allow connecting to private / loopback addresses.
    # Blocked by default in production (SSRF protection); customers can run a self-hosted instance instead.
    allow_private_scan_targets: bool | None = None  # None = allowed in development, blocked in production

    # Migrations run with an owner role; the app itself connects with a restricted role that is subject to
    # PostgreSQL row-level security. Empty = use database_url for migrations too.
    migration_database_url: str = ""
    # Name of the restricted runtime role that RLS grants are given to.
    runtime_db_role: str = "app_runtime"
    runtime_db_password: str = ""

    # Shared rate limiting / lockout state. Required in production; in-memory fallback for development.
    redis_url: str = ""

    # Reject passwords found in breach corpuses (Have I Been Pwned k-anonymity API; only a 5-character hash
    # prefix leaves the server). Fails open if the API is unreachable.
    password_breach_check: bool | None = None  # None = on in production

    # Evidence storage: "local" (encrypted files on disk) or "s3" (encrypted objects, plus SSE-KMS).
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_region: str = "ap-south-1"
    s3_kms_key_id: str = ""
    s3_prefix: str = "evidence"
    log_format: str = "plain"  # plain | json

    # Bearer token for /metrics (backend port only). Empty = open on the internal network.
    metrics_token: str = ""

    # Optional ClamAV daemon for malware scanning of uploads, e.g. "clamav:3310".
    clamav_address: str = ""

    # AI assistant (opt-in per organisation). Org data is sent to the Claude API only when an owner enables it.
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    ai_model: str = "claude-sonnet-5-5"
    ai_daily_jobs_per_org: int = 40

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_name(self) -> str:
        # The __Host- prefix makes browsers refuse the cookie unless it is Secure, host-only and path=/.
        return "__Host-session" if self.cookie_secure else "session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-csrf" if self.cookie_secure else "csrf"

    @property
    def breach_check_enabled(self) -> bool:
        return self.password_breach_check if self.password_breach_check is not None else self.is_production


@lru_cache
def get_settings() -> Settings:
    return Settings()
