from contextlib import AbstractContextManager
from typing import Any

from celery import Celery, signals
from kombu import Queue  # type: ignore[import-untyped]
from sqlalchemy import Engine

from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine
from cookfully.infrastructure.instance_lease import runtime_service_lease

settings = get_settings()
celery_app = Celery("cookfully", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=55,
    task_time_limit=60,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=200,
    task_track_started=True,
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_queues=(Queue("interactive"), Queue("bulk"), Queue("maintenance")),
    task_default_queue="interactive",
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 900},
    result_backend=None,
    imports=("cookfully.jobs.recipe_pipeline",),
)
celery_app.autodiscover_tasks(["cookfully.jobs"])

_runtime_engine: Engine | None = None
_runtime_lease: AbstractContextManager[None] | None = None


def runtime_engine() -> Engine | None:
    """Return the worker-lifetime engine after the runtime lease is acquired."""

    return _runtime_engine


@signals.worker_ready.connect  # type: ignore[untyped-decorator]
def acquire_runtime_lease(**_: Any) -> None:
    global _runtime_engine, _runtime_lease
    _runtime_engine = create_database_engine(settings)
    _runtime_lease = runtime_service_lease(_runtime_engine, settings.erasure_ledger_root)
    _runtime_lease.__enter__()


@signals.worker_shutdown.connect  # type: ignore[untyped-decorator]
def release_runtime_lease(**_: Any) -> None:
    global _runtime_engine, _runtime_lease
    if _runtime_lease is not None:
        _runtime_lease.__exit__(None, None, None)
        _runtime_lease = None
    if _runtime_engine is not None:
        _runtime_engine.dispose()
        _runtime_engine = None


@celery_app.task(name="cookfully.health", ignore_result=True)  # type: ignore[untyped-decorator]
def worker_health() -> str:
    return "ok"
