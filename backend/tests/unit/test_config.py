import pytest
from pydantic import ValidationError

from vigor_vine.infrastructure.config import Settings


def test_safe_job_policy_defaults_are_fixed() -> None:
    settings = Settings()

    assert settings.failed_import_diagnostics_enabled is False
    assert settings.failed_import_diagnostic_ttl_seconds == 86_400
    assert settings.job_attempt_timeout_seconds == 60
    assert settings.job_retry_delays_seconds == (5, 30, 120, 300)
    assert settings.job_max_attempts == 5
    assert settings.job_terminal_deadline_seconds == 900


def test_retry_delays_parse_from_environment_form() -> None:
    settings = Settings(job_retry_delays_seconds="5,30,120,300")

    assert settings.job_retry_delays_seconds == (5, 30, 120, 300)


def test_production_rejects_development_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")
