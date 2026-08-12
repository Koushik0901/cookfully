from functools import lru_cache
from ipaddress import ip_network
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, EmailStr, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Validated server-only configuration with safe local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COOKFULLY_",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["development", "test", "production"] = "development"
    instance_id: UUID = UUID("00000000-0000-7000-8000-000000000001")
    secret_key: SecretStr = SecretStr("development-only-change-before-production")
    owner_email: EmailStr = "owner@example.com"
    owner_bootstrap_password: SecretStr = SecretStr("development-only")
    database_url: str = "postgresql+psycopg://cookfully:cookfully@localhost:5432/cookfully"
    redis_url: str = "redis://localhost:6379/0"
    public_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:5173")
    api_base_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    trusted_proxy_cidrs: Annotated[tuple[str, ...], NoDecode] = ()
    media_root: Path = Path("media")
    export_root: Path = Path("exports")
    erasure_ledger_root: Path = Path("erasure-ledger")
    failed_import_diagnostics_enabled: bool = False
    failed_import_diagnostic_ttl_seconds: Literal[86_400] = 86_400
    job_attempt_timeout_seconds: Literal[60] = 60
    job_retry_delays_seconds: Annotated[tuple[int, int, int, int], NoDecode] = (5, 30, 120, 300)
    job_max_attempts: Literal[5] = 5
    job_terminal_deadline_seconds: Literal[900] = 900
    detailed_diagnostic_retention_days: Literal[30] = 30
    safe_job_metadata_retention_days: Literal[365] = 365
    retention_sweep_interval_seconds: Annotated[int, Field(ge=300, le=21_600)] = 21_600
    backup_retention_days: int = 30
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

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            ip_network(item, strict=False)
        return value

    def model_post_init(self, __context: object) -> None:
        if self.environment == "production":
            if len(self.secret_key.get_secret_value()) < 32:
                raise ValueError(
                    "COOKFULLY_SECRET_KEY must contain at least 32 characters in production"
                )
            if self.owner_bootstrap_password.get_secret_value() == "development-only":
                raise ValueError("COOKFULLY_OWNER_BOOTSTRAP_PASSWORD must be changed in production")
            if self.instance_id == UUID("00000000-0000-7000-8000-000000000001"):
                raise ValueError("COOKFULLY_INSTANCE_ID must be unique and stable in production")
            if not self.cookie_secure:
                raise ValueError("COOKFULLY_COOKIE_SECURE must be true in production")
            if self.public_base_url.scheme != "https" or self.api_base_url.scheme != "https":
                raise ValueError(
                    "COOKFULLY_PUBLIC_BASE_URL and COOKFULLY_API_BASE_URL "
                    "must use HTTPS in production"
                )
            if not self.trusted_proxy_cidrs:
                raise ValueError(
                    "COOKFULLY_TRUSTED_PROXY_CIDRS must name the production reverse proxy"
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
