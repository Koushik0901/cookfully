from __future__ import annotations

from uuid import uuid4

import pytest

from cookfully.infrastructure import nutrition_concurrency
from cookfully.infrastructure.nutrition_concurrency import NutritionConcurrencyLease


class FakeRedis:
    """Just enough Redis for slot leasing: SET NX EX and the compare-and-delete script."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        assert nx and ex > 0, "slots must be exclusive and expire"
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        assert numkeys == 1
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


def test_leases_fill_each_slot_then_refuse_when_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nutrition_concurrency.time, "sleep", lambda _: None)
    redis = FakeRedis()
    first = NutritionConcurrencyLease(redis, limit=2, job_id=uuid4())  # type: ignore[arg-type]
    second = NutritionConcurrencyLease(redis, limit=2, job_id=uuid4())  # type: ignore[arg-type]
    third = NutritionConcurrencyLease(redis, limit=2, job_id=uuid4())  # type: ignore[arg-type]

    assert first.acquire()
    assert second.acquire()
    assert len(redis.values) == 2
    # No slot left: the waiter gives up once its deadline passes instead of blocking forever.
    assert third.acquire(timeout_seconds=0) is False


def test_release_frees_the_slot_for_the_next_job() -> None:
    redis = FakeRedis()
    first = NutritionConcurrencyLease(redis, limit=1, job_id=uuid4())  # type: ignore[arg-type]
    second = NutritionConcurrencyLease(redis, limit=1, job_id=uuid4())  # type: ignore[arg-type]

    assert first.acquire()
    assert second.acquire(timeout_seconds=0) is False
    first.release()
    assert redis.values == {}
    assert second.acquire()


def test_release_never_deletes_a_slot_owned_by_another_job() -> None:
    """An expired lease must not free the slot that a newer job now holds."""

    redis = FakeRedis()
    stale = NutritionConcurrencyLease(redis, limit=1, job_id=uuid4())  # type: ignore[arg-type]
    assert stale.acquire()
    (key,) = redis.values
    redis.values[key] = "someone-else"  # the TTL expired and another job took the slot

    stale.release()

    assert redis.values == {key: "someone-else"}


def test_release_without_acquire_is_a_noop() -> None:
    redis = FakeRedis()
    NutritionConcurrencyLease(redis, limit=1, job_id=uuid4()).release()  # type: ignore[arg-type]
    assert redis.values == {}
