from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.infrastructure.models.jobs import OutboxEvent, ProcessingJob
from cookfully.infrastructure.models.recipes import Recipe


def create_job(service: JobService, aggregate_id: UUID, now: datetime) -> ProcessingJob:
    return service.accept(
        kind="nutrition_rollup",
        aggregate_type="recipe",
        aggregate_id=aggregate_id,
        input_hash="sha256:current",
        trace_id="trace-12345678",
        now=now,
    )


def test_acceptance_is_transactional_and_duplicate_delivery_is_idempotent(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    now = datetime(2026, 8, 10, tzinfo=UTC)
    aggregate_id = UUID("0198a9f0-1111-7111-8111-111111111111")
    first = create_job(service, aggregate_id, now)
    duplicate = create_job(service, aggregate_id, now)
    assert duplicate.id == first.id
    with session_factory() as session:
        assert len(session.scalars(select(ProcessingJob)).all()) == 1
        assert len(session.scalars(select(OutboxEvent)).all()) == 1


def test_fixed_retry_schedule_attempt_ceiling_and_terminal_deadline(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    accepted = datetime(2026, 8, 10, tzinfo=UTC)
    job = create_job(service, UUID("0198a9f0-2222-7222-8222-222222222222"), accepted)
    cursor = accepted
    for expected_attempt, delay in enumerate((5, 30, 120, 300), 1):
        running = service.claim(job.id, now=cursor)
        assert running.attempt == expected_attempt
        retrying = service.fail_attempt(job.id, "provider_unavailable", retryable=True, now=cursor)
        assert retrying.status == "retry_wait"
        assert retrying.next_retry_at == cursor + timedelta(seconds=delay)
        cursor = retrying.next_retry_at
        assert cursor is not None
        service.release_due_retries(now=cursor)
    service.claim(job.id, now=cursor)
    failed = service.fail_attempt(job.id, "provider_unavailable", retryable=True, now=cursor)
    assert failed.status == "failed"
    assert failed.finished_at == cursor

    deadline_job = create_job(service, UUID("0198a9f0-3333-7333-8333-333333333333"), accepted)
    expired = service.reconcile_deadlines(now=accepted + timedelta(minutes=15))
    assert deadline_job.id in expired


def test_stale_input_supersedes_and_progress_is_safe(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    now = datetime(2026, 8, 10, tzinfo=UTC)
    job = create_job(service, UUID("0198a9f0-4444-7444-8444-444444444444"), now)
    assert (
        service.claim(job.id, now=now, current_input_hash="sha256:changed").status == "superseded"
    )
    progress = service.progress(job.id)
    assert progress.status == "superseded"
    assert progress.failure_message is None


def test_stalled_job_recovery_and_retention_boundaries(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    accepted = datetime(2026, 8, 10, tzinfo=UTC)
    job = create_job(service, UUID("0198a9f0-5555-7555-8555-555555555555"), accepted)
    service.claim(job.id, now=accepted)
    assert job.id in service.requeue_stalled(now=accepted + timedelta(seconds=61))
    service.claim(job.id, now=accepted + timedelta(seconds=61))
    terminal = service.fail_attempt(
        job.id, "bad_input", retryable=False, now=accepted + timedelta(seconds=62)
    )
    assert terminal.diagnostic_reduce_at == terminal.finished_at + timedelta(days=30)
    assert terminal.safe_metadata_delete_at == terminal.finished_at + timedelta(days=365)
    assert service.reduce_diagnostics(now=terminal.diagnostic_reduce_at) == [job.id]
    assert service.delete_safe_metadata(now=terminal.safe_metadata_delete_at) == [job.id]


def test_stalled_job_at_attempt_ceiling_is_failed_without_overflow(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    accepted = datetime(2026, 8, 10, tzinfo=UTC)
    job = create_job(service, UUID("0198a9f0-6666-7666-8666-666666666666"), accepted)
    with session_factory.begin() as session:
        stored = session.get(ProcessingJob, job.id)
        assert stored is not None
        stored.status = "running"
        stored.attempt = stored.max_attempts
        stored.heartbeat_at = accepted

    stalled = service.requeue_stalled(now=accepted + timedelta(seconds=61))
    assert stalled == [job.id]
    assert service.progress(job.id).status == "failed"
    assert service.progress(job.id).failure_code == "worker_stalled"


def test_claim_defensively_fails_queued_job_at_attempt_ceiling(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    accepted = datetime(2026, 8, 10, tzinfo=UTC)
    job = create_job(service, UUID("0198a9f0-7777-7777-8777-777777777777"), accepted)
    with session_factory.begin() as session:
        stored = session.get(ProcessingJob, job.id)
        assert stored is not None
        stored.attempt = stored.max_attempts

    claimed = service.claim(job.id, now=accepted)
    assert claimed.status == "failed"
    assert claimed.failure_code == "attempt_limit_reached"


def test_deadline_reconciliation_clears_processing_recipe_projection(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    accepted = datetime(2026, 8, 10, tzinfo=UTC)
    recipe_id = UUID("0198a9f0-8888-7888-8888-888888888888")
    with session_factory.begin() as session:
        session.add(
            Recipe(
                id=recipe_id,
                title="Stalled soup",
                yield_quantity=Decimal("1.000"),
                yield_unit="servings",
                status="processing",
                nutrition_state="pending",
                input_hash="sha256:current",
                version=1,
            )
        )
    job = create_job(service, recipe_id, accepted)
    expired = service.reconcile_deadlines(now=accepted + timedelta(minutes=15))
    assert expired == [job.id]
    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.status == "failed"
        assert recipe.nutrition_state == "failed"


def test_startup_projection_reconciliation_repairs_legacy_terminal_failure(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    accepted = datetime(2026, 8, 10, tzinfo=UTC)
    recipe_id = UUID("0198a9f0-9999-7999-8999-999999999999")
    with session_factory.begin() as session:
        session.add(
            Recipe(
                id=recipe_id,
                title="Legacy stalled recipe",
                yield_quantity=Decimal("1.000"),
                yield_unit="servings",
                status="processing",
                nutrition_state="pending",
                input_hash="sha256:current",
                version=1,
            )
        )
    job = create_job(service, recipe_id, accepted)
    service.claim(job.id, now=accepted)
    service.fail_attempt(job.id, "processing_error", retryable=False, now=accepted)
    assert service.reconcile_recipe_projections() == [recipe_id]
    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        assert recipe is not None
        assert recipe.status == "failed"
        assert recipe.nutrition_state == "failed"
