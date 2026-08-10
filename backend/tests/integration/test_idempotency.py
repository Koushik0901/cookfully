from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.application.auth import AuthService
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.domain.common import DomainError


def test_idempotency_replay_conflict_abort_and_expiry(
    session_factory: sessionmaker[Session],
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "idempotency@example.com", "correct horse battery staple", "Owner"
    )
    service = IdempotencyService(session_factory)
    accepted_at = datetime(2026, 8, 10, tzinfo=UTC)
    payload = {"url": "https://example.com/recipe"}

    first = service.begin(
        owner_id=owner.id,
        key="idempotency-key-0001",
        operation="recipe.import",
        payload=payload,
        now=accepted_at,
    )
    assert first.replay is False
    with pytest.raises(DomainError) as in_progress:
        service.begin(
            owner_id=owner.id,
            key="idempotency-key-0001",
            operation="recipe.import",
            payload=payload,
            now=accepted_at + timedelta(seconds=1),
        )
    assert in_progress.value.code == "idempotency_in_progress"

    service.complete(
        owner_id=owner.id,
        key="idempotency-key-0001",
        response_status=202,
        resource_id=owner.id,
        response_body={"status": "queued", "resourceId": str(owner.id)},
        now=accepted_at + timedelta(seconds=2),
    )
    replay = service.begin(
        owner_id=owner.id,
        key="idempotency-key-0001",
        operation="recipe.import",
        payload=payload,
        now=accepted_at + timedelta(seconds=3),
    )
    assert replay.replay is True
    assert replay.response_status == 202
    assert replay.resource_id == owner.id
    assert replay.response_body == {"status": "queued", "resourceId": str(owner.id)}

    with pytest.raises(DomainError) as conflict:
        service.begin(
            owner_id=owner.id,
            key="idempotency-key-0001",
            operation="recipe.import",
            payload={"url": "https://example.com/different"},
            now=accepted_at + timedelta(seconds=4),
        )
    assert conflict.value.code == "idempotency_conflict"

    service.begin(
        owner_id=owner.id,
        key="idempotency-key-abort",
        operation="recipe.restore",
        payload={"recipeId": str(owner.id)},
        now=accepted_at,
    )
    service.abort(owner_id=owner.id, key="idempotency-key-abort")
    assert (
        service.begin(
            owner_id=owner.id,
            key="idempotency-key-abort",
            operation="recipe.restore",
            payload={"recipeId": str(owner.id)},
            now=accepted_at + timedelta(seconds=1),
        ).replay
        is False
    )

    assert service.delete_expired(now=accepted_at + timedelta(hours=24, seconds=1)) == 2
