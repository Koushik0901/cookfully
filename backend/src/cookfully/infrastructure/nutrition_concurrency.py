from __future__ import annotations

import time
from uuid import UUID

from redis import Redis


class NutritionConcurrencyLease:
    def __init__(self, redis: Redis[str], *, limit: int, job_id: UUID) -> None:
        self._redis = redis
        self._limit = limit
        self._token = str(job_id)
        self._key: str | None = None

    def acquire(self, *, timeout_seconds: float = 50) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            for slot in range(self._limit):
                key = f"cookfully:nutrition-match:slot:{slot}"
                if self._redis.set(key, self._token, nx=True, ex=120):
                    self._key = key
                    return True
            time.sleep(0.25)
        return False

    def release(self) -> None:
        if self._key is None:
            return
        self._redis.eval(  # type: ignore[no-untyped-call]
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            self._key,
            self._token,
        )
        self._key = None
