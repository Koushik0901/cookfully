"""Running Alembic must not silence the application's loggers.

``logging.config.fileConfig`` disables every logger that already exists unless told otherwise.
Anything that runs migrations inside a live process (a restore, a test) would then lose its own
log output without any error, and tests that capture logs would pass or fail depending on which
test ran before them.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from cookfully.infrastructure import config
from cookfully.infrastructure.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_the_migration_environment_leaves_existing_loggers_enabled(
    monkeypatch: pytest.MonkeyPatch, isolated_database_url: str
) -> None:
    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: Settings(environment="test", database_url=isolated_database_url),
    )
    application_logger = logging.getLogger("cookfully.migration_env_probe")
    application_logger.disabled = False
    alembic_config = Config(str(ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(ROOT / "migrations"))

    command.current(alembic_config)  # loads migrations/env.py, which configures logging

    assert application_logger.disabled is False
