"""Progressive lockout for failed sign-ins.

Cookfully has one owner, so callers track failures under one global key *and* per client address:
a guesser cannot dodge the limit by rotating addresses, and the global key means unknown emails
cannot be used to flood the table. After ``free_attempts`` consecutive
failures the key is locked for an exponentially growing time, capped at ``max_lock`` so a stranger
on the network can slow the owner down but never lock them out for long. State is in memory: it
resets on restart, which only an operator can trigger.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(slots=True)
class _Entry:
    failures: int = 0
    locked_until: float = 0.0
    last_failure: float = 0.0


class LoginThrottle:
    def __init__(
        self,
        *,
        free_attempts: int = 5,
        base_lock_seconds: float = 30.0,
        max_lock_seconds: float = 300.0,
        forget_after_seconds: float = 3600.0,
        max_entries: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._free = free_attempts
        self._base = base_lock_seconds
        self._max = max_lock_seconds
        self._forget = forget_after_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def retry_after(self, *keys: str) -> int:
        """Seconds until every key may try again; ``0`` when sign-in is allowed."""

        now = self._clock()
        with self._lock:
            remaining = max(
                (self._entries[key].locked_until - now for key in keys if key in self._entries),
                default=0.0,
            )
        return max(0, int(remaining) + (1 if remaining > 0 else 0))

    def record_failure(self, *keys: str) -> None:
        now = self._clock()
        with self._lock:
            self._evict(now)
            for key in keys:
                if key not in self._entries and len(self._entries) >= self._max_entries:
                    continue  # table full of live entries: the global key still protects
                entry = self._entries.setdefault(key, _Entry())
                if now - entry.last_failure > self._forget:
                    entry.failures = 0
                entry.failures += 1
                entry.last_failure = now
                excess = entry.failures - self._free
                if excess >= 0:
                    entry.locked_until = now + min(self._base * (2**excess), self._max)

    def record_success(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._entries.pop(key, None)

    def _evict(self, now: float) -> None:
        """Drop idle, unlocked entries; locked entries are never evicted."""

        if len(self._entries) < self._max_entries:
            return
        for key in [
            key
            for key, entry in self._entries.items()
            if entry.locked_until <= now and now - entry.last_failure > 60
        ]:
            del self._entries[key]
