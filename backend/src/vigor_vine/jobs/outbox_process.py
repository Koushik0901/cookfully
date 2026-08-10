from __future__ import annotations

import logging
import signal
import time
from types import FrameType

from vigor_vine.infrastructure.config import get_settings
from vigor_vine.infrastructure.database import create_database_engine, create_session_factory
from vigor_vine.infrastructure.instance_lease import runtime_service_lease
from vigor_vine.jobs.app import celery_app
from vigor_vine.jobs.outbox import OutboxDispatcher

logger = logging.getLogger(__name__)
running = True


def _stop(_: int, __: FrameType | None) -> None:
    global running
    running = False


def publish(payload: dict[str, object]) -> None:
    celery_app.send_task("vigor_vine.process_job", kwargs={"envelope": payload})


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    settings = get_settings()
    engine = create_database_engine(settings)
    dispatcher = OutboxDispatcher(create_session_factory(engine), publish)
    try:
        with runtime_service_lease(engine, settings.erasure_ledger_root):
            while running:
                published = dispatcher.dispatch_batch()
                if published == 0:
                    time.sleep(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
