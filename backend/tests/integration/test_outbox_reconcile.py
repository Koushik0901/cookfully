from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.jobs.outbox import OutboxDispatcher
from cookfully.jobs.outbox_process import run_once


def test_outbox_run_once_reconciles_due_retries_then_dispatches(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    now = datetime(2026, 8, 10, tzinfo=UTC)
    job = service.accept(
        kind="portable_export",
        aggregate_type="exportable",
        aggregate_id=UUID("0198a9f0-1111-7111-8111-111111111111"),
        input_hash="sha256:current",
        trace_id="trace-12345678",
        now=now,
    )
    service.claim(job.id, now=now)
    retrying = service.fail_attempt(job.id, "export_failed", retryable=True, now=now)
    assert retrying.status == "retry_wait"
    assert retrying.next_retry_at == now + timedelta(seconds=5)
    published: list[dict[str, object]] = []

    dispatcher = OutboxDispatcher(session_factory, published.append)
    assert dispatcher.dispatch_batch() == 1
    assert [event["jobId"] for event in published] == [str(job.id)]
    published.clear()

    assert run_once(dispatcher, service, now=now + timedelta(seconds=10)) == 1
    assert [event["jobId"] for event in published] == [str(job.id)]
    assert service.progress(job.id).status == "queued"
