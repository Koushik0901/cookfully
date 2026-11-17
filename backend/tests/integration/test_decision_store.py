from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.domain.decisions import Ask, Check, Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import PostgresDecisionStore, StoredAnswer
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.decisions import DecisionAnswer
from cookfully.jobs.retention import sweep_retention

ASK = Ask(Purpose.SHELF_LIFE, {"item": "kimchi"}, {"fresh": Check("Fresh?", "yes", "no")})
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


def _engine(
    session_factory: sessionmaker[Session], transport: ScriptedDecisionTransport
) -> Decisions:
    return Decisions(
        DecisionsConfig("k", Decimal("2"), {Purpose.SHELF_LIFE: FeatureConfig(models=("m1",))}),
        transport,
        PostgresDecisionStore(session_factory),
    )


def test_answers_and_cost_persist_and_replay_without_calls(
    session_factory: sessionmaker[Session],
) -> None:
    transport = ScriptedDecisionTransport(
        lambda _m, _s, _q: {"fresh": {"type": "noul", "noul": 0.25}}
    )
    first = _engine(session_factory, transport).ask([ASK])[0]
    second = _engine(session_factory, transport).ask([ASK])[0]
    assert first.check("fresh") == second.check("fresh") == Decimal("0.25")
    assert len(transport.calls) == 1
    assert PostgresDecisionStore(session_factory).spent_since(EPOCH) == Decimal("0.00003")


def test_duplicate_writes_are_ignored(session_factory: sessionmaker[Session]) -> None:
    store = PostgresDecisionStore(session_factory)
    row = StoredAnswer("p", "m1", "h" * 64, {"checks": {}}, Decimal("0.1"))
    store.put([row])
    store.put([row])
    assert store.spent_since(EPOCH) == Decimal("0.1")
    assert set(store.get([("m1", "h" * 64), ("m2", "h" * 64)])) == {("m1", "h" * 64)}


def test_retention_removes_answers_older_than_a_year(
    session_factory: sessionmaker[Session], tmp_path: Any
) -> None:
    from cookfully.application.jobs import JobService

    store = PostgresDecisionStore(session_factory)
    store.put([StoredAnswer("p", "m1", "old", {}, Decimal(0))])
    store.put([StoredAnswer("p", "m1", "new", {}, Decimal(0))])
    with session_factory.begin() as session:
        session.execute(
            update(DecisionAnswer)
            .where(DecisionAnswer.request_hash == "old")
            .values(created_at=datetime.now(UTC) - timedelta(days=400))
        )
    swept = sweep_retention(
        JobService(session_factory),
        session_factory,
        MediaStore(tmp_path, "test-secret-key-0123456789abcdef"),
    )
    assert swept["expired_decision_answers"] == 1
    assert set(store.get([("m1", "old"), ("m1", "new")])) == {("m1", "new")}
