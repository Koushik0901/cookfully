from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timedelta
from types import FrameType

from cookfully.application.jobs import JobService
from cookfully.application.reference_data import INSTALL_JOB_DEADLINE
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.instance_lease import runtime_service_lease
from cookfully.jobs.app import celery_app
from cookfully.jobs.outbox import OutboxDispatcher
from cookfully.jobs.reconciler import reconcile_jobs

logger = logging.getLogger(__name__)
running = True
INSTALL_GRACE = timedelta(minutes=5)
FOOD_EMBEDDING_SOFT_LIMIT_SECONDS = 30 * 60
FOOD_EMBEDDING_HARD_LIMIT_SECONDS = FOOD_EMBEDDING_SOFT_LIMIT_SECONDS + 60
BULK_JOB_KINDS = frozenset(
    {"food_embedding_index", "semantic_model_download", "reference_data_install"}
)
MAINTENANCE_JOB_KINDS = frozenset({"portable_export"})


def queue_for(kind: object) -> str:
    if kind in BULK_JOB_KINDS:
        return "bulk"
    if kind in MAINTENANCE_JOB_KINDS:
        return "maintenance"
    return "interactive"


def _stop(_: int, __: FrameType | None) -> None:
    global running
    running = False


def publish(payload: dict[str, object]) -> None:
    queue = queue_for(payload.get("kind"))
    if payload.get("kind") == "reference_data_install":
        celery_app.send_task(
            "cookfully.process_job",
            kwargs={"envelope": payload},
            soft_time_limit=int(INSTALL_JOB_DEADLINE.total_seconds()),
            time_limit=int(INSTALL_JOB_DEADLINE.total_seconds())
            + int(INSTALL_GRACE.total_seconds()),
            queue=queue,
        )
    elif payload.get("kind") in {"food_embedding_index", "semantic_model_download"}:
        # A full catalog rebuild embeds tens of thousands of foods and must
        # outlive the short interactive-job default (55s/60s).
        celery_app.send_task(
            "cookfully.process_job",
            kwargs={"envelope": payload},
            soft_time_limit=FOOD_EMBEDDING_SOFT_LIMIT_SECONDS,
            time_limit=FOOD_EMBEDDING_HARD_LIMIT_SECONDS,
            queue=queue,
        )
    else:
        celery_app.send_task("cookfully.process_job", kwargs={"envelope": payload}, queue=queue)


def run_once(
    dispatcher: OutboxDispatcher,
    service: JobService,
    *,
    now: datetime | None = None,
) -> int:
    reconcile_jobs(service, now=now)
    return dispatcher.dispatch_batch()


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    settings = get_settings()
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    service = JobService(sessions)
    dispatcher = OutboxDispatcher(sessions, publish)
    try:
        with runtime_service_lease(engine, settings.erasure_ledger_root):
            while running:
                published = run_once(dispatcher, service)
                if published == 0:
                    time.sleep(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
