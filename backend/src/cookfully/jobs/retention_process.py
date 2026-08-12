from __future__ import annotations

import logging
import signal
import time
from pathlib import Path
from threading import Event
from types import FrameType

from cookfully.application.jobs import JobService
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.instance_lease import runtime_service_lease
from cookfully.infrastructure.media_store import MediaStore
from cookfully.jobs.retention import sweep_retention

logger = logging.getLogger(__name__)
stop_requested = Event()
HEARTBEAT_PATH = Path("/tmp/cookfully-retention-heartbeat")


def _stop(_: int, __: FrameType | None) -> None:
    stop_requested.set()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    settings = get_settings()
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    jobs = JobService(sessions)
    media = MediaStore(settings.media_root, settings.secret_key.get_secret_value())
    try:
        with runtime_service_lease(engine, settings.erasure_ledger_root):
            while not stop_requested.is_set():
                started = time.time()
                counts = sweep_retention(jobs, sessions, media)
                HEARTBEAT_PATH.write_text(str(int(time.time())), encoding="ascii")
                logger.info("retention_sweep_complete counts=%s", counts)
                elapsed = time.time() - started
                stop_requested.wait(max(0.0, settings.retention_sweep_interval_seconds - elapsed))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
