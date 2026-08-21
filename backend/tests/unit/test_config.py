import pytest
from pydantic import ValidationError

from cookfully.infrastructure.config import Settings


def test_safe_job_policy_defaults_are_fixed() -> None:
    settings = Settings()

    assert settings.failed_import_diagnostics_enabled is False
    assert settings.failed_import_diagnostic_ttl_seconds == 86_400
    assert settings.job_attempt_timeout_seconds == 60
    assert settings.job_retry_delays_seconds == (5, 30, 120, 300)
    assert settings.job_max_attempts == 5
    assert settings.job_terminal_deadline_seconds == 900
    assert settings.retention_sweep_interval_seconds == 21_600


def test_comma_separated_values_parse_from_environment_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COOKFULLY_JOB_RETRY_DELAYS_SECONDS", "5,30,120,300")
    monkeypatch.setenv("COOKFULLY_TRUSTED_PROXY_CIDRS", "")
    settings = Settings(_env_file=None)

    assert settings.job_retry_delays_seconds == (5, 30, 120, 300)
    assert settings.trusted_proxy_cidrs == ()


def test_database_url_uses_postgres_credentials_from_env_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_USER=local user\nPOSTGRES_PASSWORD=p@ss/word\nPOSTGRES_DB=meal planner\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("COOKFULLY_DATABASE_URL", raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.database_url == (
        "postgresql+psycopg://local%20user:p%40ss%2Fword@localhost:5432/meal%20planner"
    )


def test_explicit_database_url_takes_precedence_over_postgres_credentials(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_USER=compose-user\nPOSTGRES_PASSWORD=compose-password\n",
        encoding="utf-8",
    )

    settings = Settings(
        _env_file=env_file,
        database_url="postgresql+psycopg://explicit:password@db.example/cookfully",
    )

    assert settings.database_url == "postgresql+psycopg://explicit:password@db.example/cookfully"


def test_production_rejects_development_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_production_requires_https_secure_cookies_and_valid_trusted_proxy_cidrs() -> None:
    common = {
        "environment": "production",
        "instance_id": "0198a9f0-1111-7111-8111-111111111111",
        "secret_key": "a-production-secret-that-is-longer-than-32-characters",
        "owner_bootstrap_password": "a-production-bootstrap-password",
        "cookie_secure": True,
        "trusted_proxy_cidrs": "172.31.250.10/32",
    }
    with pytest.raises(ValidationError):
        Settings(**common)
    with pytest.raises(ValidationError):
        Settings(
            **{**common, "trusted_proxy_cidrs": "not-a-network"},
            public_base_url="https://recipes.example.com",
            api_base_url="https://recipes.example.com",
        )

    settings = Settings(
        **common,
        public_base_url="https://recipes.example.com",
        api_base_url="https://recipes.example.com",
    )
    assert settings.trusted_proxy_cidrs == ("172.31.250.10/32",)
