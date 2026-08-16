from __future__ import annotations

import logging
import signal
import time
from datetime import datetime
from types import FrameType

from cookfully.application.jobs import JobService
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.instance_lease import runtime_service_lease
from cookfully.jobs.app import celery_app
from cookfully.jobs.outbox import OutboxDispatcher
from cookfully.jobs.reconciler import reconcile_jobs

logger = logging.getLogger(__name__)
running = True


def _stop(_: int, __: FrameType | None) -> None:
    global running
    running = False


def publish(payload: dict[str, object]) -> None:
    celery_app.send_task("cookfully.process_job", kwargs={"envelope": payload})


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
