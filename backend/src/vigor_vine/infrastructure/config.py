from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, EmailStr, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated server-only configuration with safe local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VV_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    secret_key: SecretStr = SecretStr("development-only-change-before-production")
    owner_email: EmailStr = "owner@example.com"
    owner_bootstrap_password: SecretStr = SecretStr("development-only")
    database_url: str = "postgresql+psycopg://vigor_vine:vigor_vine@localhost:5432/vigor_vine"
    redis_url: str = "redis://localhost:6379/0"
    public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:5173")
    api_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    trusted_proxy_cidrs: tuple[str, ...] = ()
    media_root: Path = Path("media")
    erasure_ledger_root: Path = Path("erasure-ledger")
    failed_import_diagnostics_enabled: bool = False
    failed_import_diagnostic_ttl_seconds: Literal[86_400] = 86_400
    job_attempt_timeout_seconds: Literal[60] = 60
    job_retry_delays_seconds: tuple[int, int, int, int] = (5, 30, 120, 300)
    job_max_attempts: Literal[5] = 5
    job_terminal_deadline_seconds: Literal[900] = 900
    detailed_diagnostic_retention_days: Literal[30] = 30
    safe_job_metadata_retention_days: Literal[365] = 365
    cookie_secure: bool = False

    @field_validator("job_retry_delays_seconds", mode="before")
    @classmethod
    def parse_retry_delays(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(int(item.strip()) for item in value.split(","))
        return value

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def parse_trusted_proxies(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    def model_post_init(self, __context: object) -> None:
        if self.environment == "production":
            if len(self.secret_key.get_secret_value()) < 32:
                raise ValueError("VV_SECRET_KEY must contain at least 32 characters in production")
            if self.owner_bootstrap_password.get_secret_value() == "development-only":
                raise ValueError("VV_OWNER_BOOTSTRAP_PASSWORD must be changed in production")
            if not self.cookie_secure:
                raise ValueError("VV_COOKIE_SECURE must be true in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
