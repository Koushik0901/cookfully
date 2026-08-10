from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from vigor_vine.domain.common import DomainError

INSTANCE_ADVISORY_LOCK_ID = 8_674_662_563_779_101
MAINTENANCE_STATE_NAME = "owner-erasure-maintenance.json"


def maintenance_state_path(root: Path) -> Path:
    return root.resolve() / MAINTENANCE_STATE_NAME


def ensure_activation_allowed(root: Path) -> None:
    if maintenance_state_path(root).exists():
        raise DomainError(
            "maintenance_required",
            "Owner erasure is incomplete; resume the offline erasure command before startup.",
            503,
        )


def _try_lock(connection: Connection, *, shared: bool) -> bool:
    function = "pg_try_advisory_lock_shared" if shared else "pg_try_advisory_lock"
    return bool(
        connection.scalar(
            text(f"SELECT {function}(:lock_id)"), {"lock_id": INSTANCE_ADVISORY_LOCK_ID}
        )
    )


def _unlock(connection: Connection, *, shared: bool) -> None:
    function = "pg_advisory_unlock_shared" if shared else "pg_advisory_unlock"
    connection.execute(text(f"SELECT {function}(:lock_id)"), {"lock_id": INSTANCE_ADVISORY_LOCK_ID})


@contextmanager
def runtime_service_lease(engine: Engine, ledger_root: Path) -> Iterator[None]:
    """Hold a shared lease for an active API, worker, outbox, or retention process."""

    ensure_activation_allowed(ledger_root)
    with engine.connect() as connection:
        if not _try_lock(connection, shared=True):
            raise DomainError(
                "maintenance_in_progress", "The instance is in offline maintenance mode.", 503
            )
        try:
            ensure_activation_allowed(ledger_root)
            yield
        finally:
            _unlock(connection, shared=True)


@contextmanager
def offline_maintenance_lease(engine: Engine) -> Iterator[None]:
    """Acquire the exclusive non-blocking lease required by destructive offline commands."""

    with engine.connect() as connection:
        if not _try_lock(connection, shared=False):
            raise DomainError(
                "services_running",
                "Stop the API, worker, outbox, and retention services before owner erasure.",
                409,
            )
        try:
            yield
        finally:
            _unlock(connection, shared=False)
