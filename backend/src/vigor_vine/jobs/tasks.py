from typing import Any
from uuid import UUID

from vigor_vine.application.jobs import JobService
from vigor_vine.infrastructure.config import get_settings
from vigor_vine.infrastructure.database import create_database_engine, create_session_factory
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.jobs.app import celery_app
from vigor_vine.jobs.export import run_export_job


@celery_app.task(name="vigor_vine.process_job", ignore_result=True)  # type: ignore[untyped-decorator]
def process_job(envelope: dict[str, Any]) -> None:
    """Safe common dispatcher; user-story phases register the concrete handlers."""

    allowed = {
        "schemaVersion",
        "jobId",
        "kind",
        "aggregateType",
        "aggregateId",
        "inputHash",
        "traceId",
        "requestedAt",
    }
    if set(envelope) != allowed or envelope.get("schemaVersion") != 1:
        return
    settings = get_settings()
    engine = create_database_engine(settings)
    try:
        sessions = create_session_factory(engine)
        if envelope["kind"] == "portable_export":
            run_export_job(
                sessions,
                MediaStore(settings.media_root, settings.secret_key.get_secret_value()),
                settings.export_root,
                UUID(str(envelope["jobId"])),
            )
            return
        jobs = JobService(sessions)
        job = jobs.claim(
            UUID(str(envelope["jobId"])), current_input_hash=str(envelope["inputHash"])
        )
        if job.status == "running":
            jobs.fail_attempt(
                job.id,
                "handler_not_registered",
                retryable=False,
                safe_message="This processing capability is not installed yet.",
            )
    finally:
        engine.dispose()
