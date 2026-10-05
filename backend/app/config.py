from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Anupalan"
    environment: str = "development"  # development | test | production

    database_url: str = "postgresql+psycopg://postgres@localhost:5432/app"

    # Secrets. MUST be overridden in production (startup refuses the defaults outside development).
    secret_key: str = "dev-only-insecure-secret-change-me"
    # Fernet key (32 url-safe base64 bytes) used to encrypt integration credentials at rest.
    encryption_key: str = "q8B2o0p7ihyc7m0Kp0b2xH4bW8mE5Sgo3JpS5qYz2Xw="

    access_token_minutes: int = 60 * 12
    cookie_name: str = "session"
    cookie_secure: bool = False  # set True behind HTTPS
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    storage_dir: Path = Path("./storage")
    max_upload_mb: int = 25

    load_content_on_startup: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
