"""The Celery entry point that every background job goes through.

``process_job`` decides, from a message's ``kind``, which handler runs. A mistake here does not
fail loudly: jobs simply stop being processed. These tests run it against a real database with the
slow or external collaborators (the inference client, the recipe pipeline, Redis) stubbed.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from celery.exceptions import Retry
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.intelligence_drafts import IntelligenceDraftService
from cookfully.application.jobs import JobService
from cookfully.domain.common import utc_now
from cookfully.infrastructure import nutrition_concurrency
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.intelligence import IntelligenceDraftRecord
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.intelligence.contracts import InferenceRequest, InferenceResponse, ToolCall
from cookfully.jobs import tasks
from cookfully.jobs.recipe_pipeline import PipelineResult

OWNER_ID = UUID("0198c100-1111-7111-8111-111111111111")
INPUT_HASH = "sha256:current-input"


class FakeRedis:
    """Just enough Redis for the slot lease (see test_nutrition_concurrency)."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.closed = False

    @classmethod
    def from_url(cls, *_: Any, **__: Any) -> FakeRedis:
        return FAKE_REDIS

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, _script: str, _numkeys: int, key: str, token: str) -> int:
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0

    def close(self) -> None:
        self.closed = True


FAKE_REDIS = FakeRedis()


@pytest.fixture
def worker(monkeypatch: pytest.MonkeyPatch, isolated_database_url: str, tmp_path: Path) -> Settings:
    """Settings the task reads, pointed at the test schema (it opens its own engine)."""

    settings = Settings(
        environment="test",
        database_url=isolated_database_url,
        media_root=tmp_path / "media",
        export_root=tmp_path / "exports",
    )
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "runtime_engine", lambda: None)
    FAKE_REDIS.values.clear()
    FAKE_REDIS.closed = False
    monkeypatch.setattr(tasks, "Redis", FakeRedis)
    return settings


def envelope(job: ProcessingJob | None = None, **overrides: Any) -> dict[str, Any]:
    job_id = job.id if job is not None else uuid4()
    base: dict[str, Any] = {
        "schemaVersion": 1,
        "jobId": str(job_id),
        "kind": job.kind if job is not None else "nutrition_rollup",
        "aggregateType": job.aggregate_type if job is not None else "recipe",
        "aggregateId": str(job.aggregate_id if job is not None else uuid4()),
        "inputHash": job.input_hash if job is not None else INPUT_HASH,
        "traceId": "trace-12345678",
        "requestedAt": "2026-08-10T00:00:00Z",
    }
    return base | overrides


def accept(
    sessions: sessionmaker[Session],
    kind: str,
    aggregate_id: UUID | None = None,
    accepted_at: datetime | None = None,
) -> ProcessingJob:
    return JobService(sessions).accept(
        now=accepted_at,
        kind=kind,
        aggregate_type="intelligence_draft" if kind.startswith("intelligence") else "job",
        aggregate_id=aggregate_id or uuid4(),
        input_hash=INPUT_HASH,
        trace_id="trace-12345678",
    )


def reload_job(sessions: sessionmaker[Session], job: ProcessingJob) -> ProcessingJob:
    with sessions() as session:
        return session.get_one(ProcessingJob, job.id)


# --- Messages that are not ours -------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda message: message | {"unexpected": "field"},
        lambda message: {key: value for key, value in message.items() if key != "traceId"},
        lambda message: message | {"schemaVersion": 2},
    ],
    ids=["extra-field", "missing-field", "unknown-schema-version"],
)
def test_messages_that_break_the_contract_are_dropped_untouched(
    worker: Settings, monkeypatch: pytest.MonkeyPatch, mutate: Callable[[dict[str, Any]], Any]
) -> None:
    def explode(*_: Any, **__: Any) -> None:
        raise AssertionError("a malformed message must not reach a handler")

    for name in (
        "run_export_job",
        "run_suggestion_job",
        "run_reference_data_install_job",
        "run_food_embedding_job",
        "run_model_download_job",
        "get_recipe_pipeline",
    ):
        monkeypatch.setattr(tasks, name, explode)

    assert tasks.process_job.run(mutate(envelope(kind="portable_export"))) is None


# --- Kinds with a dedicated handler ---------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "handler"),
    [
        ("portable_export", "run_export_job"),
        ("suggestion", "run_suggestion_job"),
        ("reference_data_install", "run_reference_data_install_job"),
        ("food_embedding_index", "run_food_embedding_job"),
        ("semantic_model_download", "run_model_download_job"),
    ],
)
def test_each_kind_is_routed_to_its_own_handler_with_the_job_id(
    worker: Settings, monkeypatch: pytest.MonkeyPatch, kind: str, handler: str
) -> None:
    calls: dict[str, tuple[Any, ...]] = {}
    for name in (
        "run_export_job",
        "run_suggestion_job",
        "run_reference_data_install_job",
        "run_food_embedding_job",
        "run_model_download_job",
    ):
        monkeypatch.setattr(tasks, name, lambda *args, _name=name: calls.__setitem__(_name, args))
    job_id = uuid4()

    result = tasks.process_job.run(envelope(kind=kind, jobId=str(job_id)))

    assert result is None
    assert list(calls) == [handler], "exactly one handler runs"
    assert calls[handler][-1] == job_id, "the handler is told which job to process"


def test_an_export_job_gets_the_media_store_and_export_directory(
    worker: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[Any, ...]] = []
    monkeypatch.setattr(tasks, "run_export_job", lambda *args: seen.append(args))

    tasks.process_job.run(envelope(kind="portable_export"))

    (_, media_store, export_root, _) = seen[0]
    assert export_root == worker.export_root
    assert media_store.__class__.__name__ == "MediaStore"


# --- Kinds with no handler ------------------------------------------------------------------


def test_a_kind_nobody_handles_fails_the_job_instead_of_leaving_it_running(
    worker: Settings, session_factory: sessionmaker[Session]
) -> None:
    job = accept(session_factory, "mystery_kind")

    assert tasks.process_job.run(envelope(job)) is None

    failed = reload_job(session_factory, job)
    assert failed.status == "failed"
    assert failed.failure_code == "handler_not_registered"


def test_a_stale_message_for_an_unhandled_kind_is_superseded_not_failed(
    worker: Settings, session_factory: sessionmaker[Session]
) -> None:
    job = accept(session_factory, "mystery_kind")

    tasks.process_job.run(envelope(job, inputHash="sha256:something-newer"))

    assert reload_job(session_factory, job).status == "superseded"


# --- Recipe pipeline ------------------------------------------------------------------------


class StubPipeline:
    def __init__(self, result: PipelineResult) -> None:
        self.result = result
        self.processed: list[Any] = []

    async def process(self, envelope: Any) -> PipelineResult:
        self.processed.append(envelope)
        return self.result


def test_recipe_jobs_run_the_pipeline_and_report_the_next_job(
    worker: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    next_job = uuid4()
    pipeline = StubPipeline(
        PipelineResult(job_id=uuid4(), status="succeeded", next_job_id=next_job)
    )
    monkeypatch.setattr(tasks, "get_recipe_pipeline", lambda: pipeline)

    result = tasks.process_job.run(envelope(kind="ingredient_parse"))

    assert result == {
        "jobId": str(pipeline.result.job_id),
        "status": "succeeded",
        "nextJobId": str(next_job),
    }
    assert pipeline.processed[0].kind == "ingredient_parse"
    assert not FAKE_REDIS.values, "only nutrition matching takes a concurrency slot"


def test_the_last_recipe_job_reports_no_next_job(
    worker: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = StubPipeline(PipelineResult(job_id=uuid4(), status="succeeded"))
    monkeypatch.setattr(tasks, "get_recipe_pipeline", lambda: pipeline)

    result = tasks.process_job.run(envelope(kind="nutrition_rollup"))

    assert result is not None
    assert result["nextJobId"] is None


def test_nutrition_matching_holds_a_slot_while_it_runs_and_frees_it_after(
    worker: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    held_during_run: list[dict[str, str]] = []

    class ObservingPipeline(StubPipeline):
        async def process(self, envelope: Any) -> PipelineResult:
            held_during_run.append(dict(FAKE_REDIS.values))
            return await super().process(envelope)

    pipeline = ObservingPipeline(PipelineResult(job_id=uuid4(), status="succeeded"))
    monkeypatch.setattr(tasks, "get_recipe_pipeline", lambda: pipeline)

    tasks.process_job.run(envelope(kind="nutrition_match"))

    assert len(held_during_run[0]) == 1, "one slot is held while the job runs"
    assert FAKE_REDIS.values == {}, "and it is released afterwards"
    assert FAKE_REDIS.closed


def test_nutrition_matching_retries_instead_of_running_when_every_slot_is_busy(
    worker: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    FAKE_REDIS.values["cookfully:nutrition-match:slot:0"] = "another-job"  # the only slot
    clock = iter([0.0, 1_000.0])  # the 50 s wait for a slot has long expired
    monkeypatch.setattr(
        nutrition_concurrency,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None),
    )

    def explode() -> None:
        raise AssertionError("the pipeline must not run without a slot")

    monkeypatch.setattr(tasks, "get_recipe_pipeline", explode)

    with pytest.raises(Retry):
        tasks.process_job.run(envelope(kind="nutrition_match"))

    assert FAKE_REDIS.values == {"cookfully:nutrition-match:slot:0": "another-job"}, (
        "the other job's slot is left alone"
    )
    assert FAKE_REDIS.closed


def test_nutrition_matching_uses_the_configured_concurrency(
    worker: Settings, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with session_factory.begin() as session:
        session.add(
            NutritionIntelligenceSettings(
                id=1, backend="hashing", model_name="BAAI/bge-small-en-v1.5", concurrency=2
            )
        )
    FAKE_REDIS.values["cookfully:nutrition-match:slot:0"] = "another-job"
    pipeline = StubPipeline(PipelineResult(job_id=uuid4(), status="succeeded"))
    monkeypatch.setattr(tasks, "get_recipe_pipeline", lambda: pipeline)

    result = tasks.process_job.run(envelope(kind="nutrition_match"))

    assert result is not None, "the second of two configured slots was free"
    assert FAKE_REDIS.values == {"cookfully:nutrition-match:slot:0": "another-job"}


# --- Local-intelligence drafts --------------------------------------------------------------


class FakeInference:
    def __init__(self, response: InferenceResponse) -> None:
        self.response = response
        self.requests: list[InferenceRequest] = []

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        self.requests.append(request)
        return self.response


Install = Callable[[InferenceResponse], FakeInference]


@pytest.fixture
def intelligence(
    worker: Settings, session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Install:
    with session_factory.begin() as session:
        session.add(
            OwnerAccount(
                id=OWNER_ID,
                email="drafts@example.com",
                display_name="Draft Owner",
                password_hash="not-used",
                timezone="UTC",
                week_starts_on=1,
            )
        )

    def install(response: InferenceResponse) -> FakeInference:
        client = FakeInference(response)
        monkeypatch.setattr(tasks, "_intelligence_client", lambda settings: client)
        return client

    return install


def queue_extraction(
    sessions: sessionmaker[Session],
    kind: str = "intelligence_recipe_extract",
    accepted_at: datetime | None = None,
) -> tuple[ProcessingJob, UUID]:
    draft = IntelligenceDraftService(sessions).create_pending(
        OWNER_ID,
        operation="recipe_extract",
        payload={
            "prompt": "2 cups flour, 1 tsp salt",
            "system": "Extract ingredients.",
            "context": {"source": "paste"},
            "tools": [
                {
                    "name": "recipe",
                    "description": "Extract a recipe",
                    "parameters": {"type": "object"},
                }
            ],
        },
    )
    return accept(sessions, kind, draft.id, accepted_at), draft.id


def reload_draft(sessions: sessionmaker[Session], draft_id: UUID) -> IntelligenceDraftRecord:
    with sessions() as session:
        return session.get_one(IntelligenceDraftRecord, draft_id)


def test_a_successful_extraction_becomes_a_draft_for_review(
    session_factory: sessionmaker[Session],
    intelligence: Install,
) -> None:
    client = intelligence(
        InferenceResponse(
            requestId="r",
            status="ok",
            model="needle2",
            confidence=0.91,
            reasoning="two ingredients",
            functionCalls=(ToolCall(name="recipe", arguments={"ingredients": ["2 cups flour"]}),),
        )
    )
    job, draft_id = queue_extraction(session_factory)

    assert tasks.process_job.run(envelope(job)) is None

    request = client.requests[0]
    assert request.prompt == "2 cups flour, 1 tsp salt"
    assert request.system == "Extract ingredients."
    assert request.context == {"source": "paste"}
    assert [tool.name for tool in request.tools] == ["recipe"]
    draft = reload_draft(session_factory, draft_id)
    assert (draft.status, draft.confidence) == ("review", 0.91)
    assert draft.payload["functionCalls"] == [
        {"name": "recipe", "arguments": {"ingredients": ["2 cups flour"]}}
    ]
    assert reload_job(session_factory, job).status == "succeeded"


def test_an_unsupported_extraction_is_recorded_as_such_not_as_a_failure(
    session_factory: sessionmaker[Session],
    intelligence: Install,
) -> None:
    intelligence(InferenceResponse(requestId="r", status="unsupported"))
    job, draft_id = queue_extraction(session_factory, "intelligence_pantry_extract")

    tasks.process_job.run(envelope(job))

    assert reload_draft(session_factory, draft_id).status == "unsupported"
    assert reload_job(session_factory, job).status == "succeeded"


def test_an_unavailable_model_schedules_a_retry_and_keeps_the_draft_waiting(
    session_factory: sessionmaker[Session],
    intelligence: Install,
) -> None:
    intelligence(InferenceResponse(requestId="r", status="unavailable", errorCode="model_loading"))
    job, draft_id = queue_extraction(session_factory)

    tasks.process_job.run(envelope(job))

    retrying = reload_job(session_factory, job)
    assert (retrying.status, retrying.failure_code) == ("retry_wait", "model_loading")
    assert reload_draft(session_factory, draft_id).status == "processing"


def test_the_final_unavailable_attempt_fails_the_draft_visibly(
    session_factory: sessionmaker[Session],
    intelligence: Install,
) -> None:
    intelligence(InferenceResponse(requestId="r", status="unavailable"))
    # Accepted 14 minutes ago (the deadline is 15), so the earlier retry delays are all in the past.
    started = utc_now() - timedelta(minutes=14)
    job, draft_id = queue_extraction(session_factory, accepted_at=started)
    jobs = JobService(session_factory)
    cursor = started
    for _ in range(job.max_attempts - 1):  # earlier attempts have already failed
        jobs.claim(job.id, now=cursor)
        retrying = jobs.fail_attempt(job.id, "intelligence_unavailable", retryable=True, now=cursor)
        assert retrying.next_retry_at is not None
        cursor = retrying.next_retry_at
        jobs.release_due_retries(now=cursor)

    tasks.process_job.run(envelope(job))

    assert reload_job(session_factory, job).status == "failed"
    draft = reload_draft(session_factory, draft_id)
    assert (draft.status, draft.failure_code) == ("failed", "intelligence_unavailable")


def test_a_missing_draft_fails_the_job_without_calling_the_model(
    session_factory: sessionmaker[Session],
    intelligence: Install,
) -> None:
    client = intelligence(InferenceResponse(requestId="r", status="ok"))
    job = accept(session_factory, "intelligence_recipe_extract", aggregate_id=uuid4())

    assert tasks.process_job.run(envelope(job)) is None

    assert reload_job(session_factory, job).failure_code == "intelligence_draft_not_found"
    assert client.requests == []


def test_turning_intelligence_off_fails_queued_extractions_with_a_clear_message(
    session_factory: sessionmaker[Session],
    intelligence: Install,
) -> None:
    client = intelligence(InferenceResponse(requestId="r", status="ok"))
    with session_factory.begin() as session:
        session.add(
            NutritionIntelligenceSettings(
                id=1,
                backend="hashing",
                model_name="BAAI/bge-small-en-v1.5",
                intelligence_enabled=False,
            )
        )
    job, _ = queue_extraction(session_factory)

    tasks.process_job.run(envelope(job))

    failed = reload_job(session_factory, job)
    assert (failed.status, failed.failure_code) == ("failed", "intelligence_disabled")
    assert failed.failure_message == "Local intelligence is turned off in Settings."
    assert client.requests == []


def test_a_job_that_is_no_longer_current_is_not_processed(
    session_factory: sessionmaker[Session],
    intelligence: Install,
) -> None:
    client = intelligence(InferenceResponse(requestId="r", status="ok"))
    job, draft_id = queue_extraction(session_factory)

    tasks.process_job.run(envelope(job, inputHash="sha256:superseded-by-newer-input"))

    assert reload_job(session_factory, job).status == "superseded"
    assert reload_draft(session_factory, draft_id).status == "queued"
    assert client.requests == []


# --- The shared inference client ------------------------------------------------------------


def test_one_inference_client_is_shared_per_configuration_and_closed_at_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[Any] = []

    class RecordingClient:
        def __init__(self, url: str, key: str, *, enabled: bool, timeout_seconds: float) -> None:
            self.args = (url, key, enabled, timeout_seconds)
            self.closed = False
            created.append(self)

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(tasks, "IntelligenceClient", RecordingClient)
    monkeypatch.setattr(tasks, "_intelligence_clients", {})
    settings = Settings(environment="test", intelligence_url="http://intelligence:8091")
    other = Settings(environment="test", intelligence_url="http://elsewhere:8091")

    first = tasks._intelligence_client(settings)
    assert tasks._intelligence_client(settings) is first, "reused, not rebuilt per job"
    assert tasks._intelligence_client(other) is not first, "a different service gets its own"
    assert len(created) == 2

    tasks._close_intelligence_clients()

    assert all(client.closed for client in created)
    assert tasks._intelligence_clients == {}


def test_the_worker_engine_is_borrowed_but_a_fallback_engine_is_owned(
    monkeypatch: pytest.MonkeyPatch, isolated_database_url: str
) -> None:
    settings = Settings(environment="test", database_url=isolated_database_url)
    shared = object()
    monkeypatch.setattr(tasks, "runtime_engine", lambda: shared)
    assert tasks._acquire_engine(settings) == (shared, False), "never disposed by the task"

    monkeypatch.setattr(tasks, "runtime_engine", lambda: None)
    engine, owned = tasks._acquire_engine(settings)
    try:
        assert owned is True, "the task must dispose an engine it created"
    finally:
        engine.dispose()
