import asyncio
from typing import Any
from uuid import UUID

from redis import Redis

from cookfully.application.jobs import JobService
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.nutrition_concurrency import NutritionConcurrencyLease
from cookfully.jobs.app import celery_app
from cookfully.jobs.export import run_export_job
from cookfully.jobs.recipe_pipeline import JobEnvelope, get_recipe_pipeline
from cookfully.jobs.reference_data_install import run_reference_data_install_job
from cookfully.jobs.suggestions import run_suggestion_job

RECIPE_KINDS = frozenset(
    {"recipe_import", "ingredient_parse", "nutrition_match", "nutrition_rollup"}
)


@celery_app.task(bind=True, name="cookfully.process_job", ignore_result=True)  # type: ignore[untyped-decorator]
def process_job(self: Any, envelope: dict[str, Any]) -> dict[str, str | None] | None:
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
        settings = get_settings()
        engine = create_database_engine(settings)
        lease: NutritionConcurrencyLease | None = None
        redis_client: Redis[str] | None = None
        try:
            if parsed.kind == "nutrition_match":
                with create_session_factory(engine)() as session:
                    configured = session.get(NutritionIntelligenceSettings, 1)
                    limit = configured.concurrency if configured is not None else 1
                redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
                lease = NutritionConcurrencyLease(
                    redis_client,
                    limit=limit,
                    job_id=parsed.job_id,
                )
                if not lease.acquire():
                    raise self.retry(countdown=1, max_retries=None)
            result = asyncio.run(get_recipe_pipeline().process(parsed))
            return {
                "jobId": str(result.job_id),
                "status": result.status,
                "nextJobId": str(result.next_job_id) if result.next_job_id else None,
            }
        finally:
            if lease is not None:
                lease.release()
            if redis_client is not None:
                redis_client.close()
            engine.dispose()
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
