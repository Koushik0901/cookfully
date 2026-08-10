from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.application.jobs import JobService
from vigor_vine.infrastructure.models.jobs import OutboxEvent, ProcessingJob


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
