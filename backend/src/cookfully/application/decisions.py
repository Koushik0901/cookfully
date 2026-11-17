"""The decision engine: the one place features ask decision models anything.

``Decisions.ask`` takes a list of ``Ask`` and returns one ``Answers`` per ask, in order. Behind that
single method it resolves the owner's settings, fans each ask out to the feature's model panel,
serves repeats from the cache, enforces the monthly spend cap, shuffles choice options, validates
answers and degrades to empty answers on any failure.

Callers must treat empty answers as "no opinion" and keep their deterministic result, or, for a
safety check, as "not checked" (never as "safe"). ``ask`` blocks until every call has finished or
timed out; use it from background jobs, or from an API route only for one small request.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import utc_now
from cookfully.domain.decisions import (
    Answers,
    Ask,
    ModelAnswers,
    Purpose,
    parse_answers,
    request_hash,
    wire_questions,
)
from cookfully.infrastructure.decision_client import OpenRouterDecisionTransport, RawDecision
from cookfully.infrastructure.decision_store import REJECTED, PostgresDecisionStore, StoredAnswer

logger = logging.getLogger(__name__)

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DECISION_TIMEOUT_SECONDS = 8.0
DEFAULT_MONTHLY_CAP_USD = Decimal("2.00")
DEFAULT_MODEL = "typesafe/jev-1.14"
DEFAULT_PANEL = ("typesafe/jev-1.14", "cloudflare/clef")
MAX_WORKERS = 8


class DecisionTransport(Protocol):
    def post(
        self,
        model: str,
        state: Mapping[str, str],
        questions: Mapping[str, Mapping[str, object]],
    ) -> RawDecision | None: ...


class DecisionStore(Protocol):
    def get(self, keys: Sequence[tuple[str, str]]) -> dict[tuple[str, str], StoredAnswer]: ...

    def put(self, rows: Sequence[StoredAnswer]) -> None: ...

    def spent_since(self, since: datetime) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class FeatureConfig:
    enabled: bool = True
    models: tuple[str, ...] = (DEFAULT_MODEL,)


# Every feature is on by default with the two-model panel measured in PR #12.
DEFAULT_FEATURES: Mapping[Purpose, FeatureConfig] = {
    purpose: FeatureConfig(True, DEFAULT_PANEL) for purpose in Purpose
}


@dataclass(frozen=True, slots=True)
class DecisionsConfig:
    """Resolved owner settings. Without an API key every answer is empty."""

    api_key: str | None
    monthly_cap_usd: Decimal = DEFAULT_MONTHLY_CAP_USD
    features: Mapping[Purpose, FeatureConfig] = field(default_factory=dict)

    def feature(self, purpose: Purpose) -> FeatureConfig:
        return self.features.get(purpose) or DEFAULT_FEATURES[purpose]

    def active(self, purpose: Purpose) -> bool:
        feature = self.feature(purpose)
        return self.api_key is not None and feature.enabled and bool(feature.models)


@dataclass(frozen=True, slots=True)
class _Job:
    ask_index: int
    model: str
    request_hash: str


class Decisions:
    def __init__(
        self,
        config: DecisionsConfig,
        transport: DecisionTransport | None,
        store: DecisionStore,
        *,
        max_workers: int = MAX_WORKERS,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._config = config
        self._transport = transport
        self._store = store
        self._max_workers = max_workers
        self._clock = clock

    @property
    def config(self) -> DecisionsConfig:
        return self._config

    def active(self, purpose: Purpose) -> bool:
        """Whether asks for ``purpose`` can get answers at all (key present, feature on)."""

        return self._transport is not None and self._config.active(purpose)

    def ask(self, asks: Sequence[Ask]) -> list[Answers]:
        collected: list[dict[str, ModelAnswers]] = [{} for _ in asks]
        jobs = [
            _Job(index, model, request_hash(model, ask))
            for index, ask in enumerate(asks)
            if self.active(ask.purpose)
            for model in self._config.feature(ask.purpose).models
        ]
        if not jobs:
            return [Answers() for _ in asks]

        cached = self._store.get([(job.model, job.request_hash) for job in jobs])
        pending: dict[tuple[str, str], list[_Job]] = {}
        for job in jobs:
            key = (job.model, job.request_hash)
            stored = cached.get(key)
            if stored is None:
                pending.setdefault(key, []).append(job)
                continue
            answers = _stored_answers(stored)
            if answers is not None:
                collected[job.ask_index][job.model] = answers

        if pending:
            self._call(asks, pending, collected)
        return [Answers(by_model) for by_model in collected]

    def _call(
        self,
        asks: Sequence[Ask],
        pending: Mapping[tuple[str, str], list[_Job]],
        collected: list[dict[str, ModelAnswers]],
    ) -> None:
        transport = self._transport
        if transport is None:
            return
        remaining = self._config.monthly_cap_usd - self._store.spent_since(
            _month_start(self._clock())
        )
        if remaining <= 0:
            logger.warning("Decision spend cap reached; %d requests skipped.", len(pending))
            return
        keys = list(pending)
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            for start in range(0, len(keys), self._max_workers):
                if remaining <= 0:
                    logger.warning(
                        "Decision spend cap reached; %d requests skipped.", len(keys) - start
                    )
                    return
                chunk = keys[start : start + self._max_workers]
                futures = [
                    pool.submit(self._post, transport, asks[pending[key][0].ask_index], key)
                    for key in chunk
                ]
                rows: list[StoredAnswer] = []
                for key, future in zip(chunk, futures, strict=True):
                    first = pending[key][0]
                    ask = asks[first.ask_index]
                    raw = future.result()
                    if raw is None:
                        continue
                    parsed = parse_answers(ask, raw.answers)
                    if parsed is None:
                        logger.warning("Decision answer from %s failed validation.", first.model)
                    rows.append(
                        StoredAnswer(
                            ask.purpose.value,
                            first.model,
                            first.request_hash,
                            parsed.to_json() if parsed is not None else dict(REJECTED),
                            raw.cost_usd,
                            raw.served_model,
                        )
                    )
                    remaining -= raw.cost_usd
                    if parsed is not None:
                        for job in pending[key]:
                            collected[job.ask_index][job.model] = parsed
                self._store.put(rows)

    @staticmethod
    def _post(transport: DecisionTransport, ask: Ask, key: tuple[str, str]) -> RawDecision | None:
        model, digest = key
        try:
            return transport.post(model, ask.state, wire_questions(ask, shuffle_seed=digest))
        except Exception:
            logger.exception("Decision transport raised for %s.", model)
            return None


def _stored_answers(stored: StoredAnswer) -> ModelAnswers | None:
    if stored.answers.get("rejected"):
        return None
    return ModelAnswers.from_json(stored.answers)


def _month_start(now: datetime) -> datetime:
    current = now.astimezone(UTC)
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def build_decisions(
    session_factory: sessionmaker[Session], config: DecisionsConfig | None = None
) -> Decisions:
    """The engine configured from the owner's Settings (or ``config`` when already loaded)."""

    if config is None:
        from cookfully.application.openrouter_settings import decisions_config, load_config

        with session_factory() as session:
            config = decisions_config(load_config(session))
    transport = (
        OpenRouterDecisionTransport(
            api_key=config.api_key, url=DECISIONS_URL, timeout_seconds=DECISION_TIMEOUT_SECONDS
        )
        if config.api_key
        else None
    )
    return Decisions(config, transport, PostgresDecisionStore(session_factory))
