import asyncio
import atexit
from typing import Any
from uuid import UUID

from redis import Redis

from cookfully.application.food_embedding_index import run_food_embedding_job
from cookfully.application.intelligence_drafts import IntelligenceDraftService
from cookfully.application.jobs import JobService
from cookfully.application.model_download import run_model_download_job
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.intelligence import IntelligenceDraftRecord
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.nutrition_concurrency import NutritionConcurrencyLease
from cookfully.intelligence.client import IntelligenceClient
from cookfully.intelligence.contracts import InferenceRequest, ToolDefinition
from cookfully.jobs.app import celery_app, runtime_engine
from cookfully.jobs.export import run_export_job
from cookfully.jobs.recipe_pipeline import JobEnvelope, get_recipe_pipeline
from cookfully.jobs.reference_data_install import run_reference_data_install_job
from cookfully.jobs.suggestions import run_suggestion_job

RECIPE_KINDS = frozenset(
    {"recipe_import", "ingredient_parse", "nutrition_match", "nutrition_rollup"}
)
INTELLIGENCE_KINDS = frozenset({"intelligence_recipe_extract", "intelligence_pantry_extract"})
_intelligence_clients: dict[tuple[str, str, bool, float], IntelligenceClient] = {}


def _acquire_engine(settings: Any) -> tuple[Any, bool]:
    """Use the worker-lifetime engine when available; own fallback engines in tests."""

    shared = runtime_engine()
    if shared is not None:
        return shared, False
    return create_database_engine(settings), True


def _intelligence_client(settings: Any) -> IntelligenceClient:
    key = (
        str(settings.intelligence_url),
        settings.intelligence_service_key.get_secret_value(),
        settings.intelligence_enabled,
        settings.intelligence_timeout_seconds,
    )
    client = _intelligence_clients.get(key)
    if client is None:
        client = IntelligenceClient(
            key[0],
            key[1],
            enabled=key[2],
            timeout_seconds=key[3],
        )
        _intelligence_clients[key] = client
    return client


@atexit.register
def _close_intelligence_clients() -> None:
    for client in _intelligence_clients.values():
        client.close()
    _intelligence_clients.clear()


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
        engine, owns_engine = _acquire_engine(settings)
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
            if owns_engine:
                engine.dispose()
    if envelope["kind"] in INTELLIGENCE_KINDS:
        settings = get_settings()
        engine, owns_engine = _acquire_engine(settings)
        try:
            sessions = create_session_factory(engine)
            jobs = JobService(sessions)
            job_id = UUID(str(envelope["jobId"]))
            job = jobs.claim(job_id, current_input_hash=str(envelope["inputHash"]))
            if job.status != "running":
                return None
            with sessions() as session:
                draft = session.get(IntelligenceDraftRecord, UUID(str(envelope["aggregateId"])))
            if draft is None:
                jobs.fail_attempt(job_id, "intelligence_draft_not_found", retryable=False)
                return None
            draft_service = IntelligenceDraftService(sessions)
            draft_service.mark_processing(draft.id)
            value = draft.payload
            tools = tuple(ToolDefinition.model_validate(item) for item in value.get("tools", ()))
            inference = _intelligence_client(settings).infer(
                InferenceRequest(
                    requestId=f"job-{job_id}",
                    operation=draft.operation,
                    prompt=str(value["prompt"]),
                    context={str(k): str(v) for k, v in value.get("context", {}).items()},
                    tools=tools,
                )
            )
            if inference.status == "unavailable":
                failed_job = jobs.fail_attempt(
                    job_id,
                    inference.error_code or "intelligence_unavailable",
                    retryable=True,
                    safe_message="Local intelligence is temporarily unavailable.",
                )
                if failed_job.status == "failed":
                    draft_service.fail_pending(
                        draft.id,
                        code=inference.error_code or "intelligence_unavailable",
                        message="Local intelligence could not complete this extraction.",
                    )
            else:
                draft_service.complete_pending(
                    draft.id,
                    status="review" if inference.status == "ok" else "unsupported",
                    confidence=inference.confidence,
                    payload={
                        "model": inference.model,
                        "reasoning": inference.reasoning,
                        "functionCalls": [
                            call.model_dump(mode="json") for call in inference.function_calls
                        ],
                        "context": value.get("context", {}),
                    },
                )
                jobs.succeed(job_id)
            return None
        finally:
            if owns_engine:
                engine.dispose()
    settings = get_settings()
    engine, owns_engine = _acquire_engine(settings)
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
        if envelope["kind"] == "food_embedding_index":
            run_food_embedding_job(sessions, UUID(str(envelope["jobId"])))
            return None
        if envelope["kind"] == "semantic_model_download":
            run_model_download_job(sessions, UUID(str(envelope["jobId"])))
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
        if owns_engine:
            engine.dispose()
