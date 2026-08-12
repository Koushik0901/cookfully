from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.infrastructure.models.jobs import OutboxEvent
from cookfully.jobs.outbox import OutboxDispatcher


def test_one_second_acceptance_broker_outage_and_recovery(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    started = perf_counter()
    job = service.accept(
        kind="recipe_import",
        aggregate_type="recipe",
        aggregate_id=UUID("0198a9f0-6666-7666-8666-666666666666"),
        input_hash="sha256:input",
        trace_id="trace-12345678",
    )
    assert perf_counter() - started < 1

    attempts = 0

    def unavailable(_: dict[str, object]) -> None:
        nonlocal attempts
        attempts += 1
        raise ConnectionError("broker unavailable")

    dispatcher = OutboxDispatcher(session_factory, unavailable)
    assert dispatcher.dispatch_batch() == 0
    with session_factory() as session:
        event = session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == job.id))
        assert event is not None and event.published_at is None and event.publish_attempts == 1

    published: list[dict[str, object]] = []
    dispatcher = OutboxDispatcher(session_factory, published.append)
    assert dispatcher.dispatch_batch() == 1
    assert published[0]["jobId"] == str(job.id)


def test_worker_death_duplicate_and_reload_polling_contract(
    session_factory: sessionmaker[Session],
) -> None:
    service = JobService(session_factory)
    now = datetime(2026, 8, 10, tzinfo=UTC)
    job = service.accept(
        kind="nutrition_rollup",
        aggregate_type="recipe",
        aggregate_id=UUID("0198a9f0-7777-7777-8777-777777777777"),
        input_hash="sha256:input",
        trace_id="trace-12345678",
        now=now,
    )
    service.claim(job.id, now=now)
    service.succeed(job.id, now=now + timedelta(seconds=1))
    assert service.claim(job.id, now=now + timedelta(seconds=2)).status == "succeeded"
    assert service.progress(job.id).status == "succeeded"
