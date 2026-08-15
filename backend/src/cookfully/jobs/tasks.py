import asyncio
from typing import Any
from uuid import UUID

from cookfully.application.jobs import JobService
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.media_store import MediaStore
from cookfully.jobs.app import celery_app
from cookfully.jobs.export import run_export_job
from cookfully.jobs.recipe_pipeline import JobEnvelope, get_recipe_pipeline
from cookfully.jobs.reference_data_install import run_reference_data_install_job
from cookfully.jobs.suggestions import run_suggestion_job

RECIPE_KINDS = frozenset(
    {"recipe_import", "ingredient_parse", "nutrition_match", "nutrition_rollup"}
)


@celery_app.task(name="cookfully.process_job", ignore_result=True)  # type: ignore[untyped-decorator]
def process_job(envelope: dict[str, Any]) -> dict[str, str | None] | None:
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
        return None
    if envelope["kind"] in RECIPE_KINDS:
        parsed = JobEnvelope.model_validate(envelope)
        result = asyncio.run(get_recipe_pipeline().process(parsed))
        return {
            "jobId": str(result.job_id),
            "status": result.status,
            "nextJobId": str(result.next_job_id) if result.next_job_id else None,
        }
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
            return None
        if envelope["kind"] == "suggestion":
            run_suggestion_job(sessions, UUID(str(envelope["jobId"])))
            return None
        if envelope["kind"] == "reference_data_install":
            run_reference_data_install_job(sessions, UUID(str(envelope["jobId"])))
            return None
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
        return None
    finally:
        engine.dispose()
