"""Where decision answers are cached and their cost is recorded.

``PostgresDecisionStore`` is the production adapter (table ``decision_answers``). It commits in its
own transaction so spend is recorded even when the caller's transaction later rolls back.
``InMemoryDecisionStore`` serves unit tests and offline replay.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import utc_now, uuid7
from cookfully.infrastructure.models.decisions import DecisionAnswer

# Stored in place of answers when a response was paid for but failed validation. It still counts
# toward spend, and replays as "no answer".
REJECTED: dict[str, Any] = {"rejected": True}


@dataclass(frozen=True, slots=True)
class StoredAnswer:
    purpose: str
    model: str
    request_hash: str
    answers: dict[str, Any]
    cost_usd: Decimal
    served_model: str | None = None


class PostgresDecisionStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, keys: Sequence[tuple[str, str]]) -> dict[tuple[str, str], StoredAnswer]:
        if not keys:
            return {}
        wanted = set(keys)
        with self._session_factory() as session:
            rows = session.scalars(
                select(DecisionAnswer).where(
                    DecisionAnswer.request_hash.in_({key[1] for key in wanted})
                )
            ).all()
            return {
                (row.model, row.request_hash): StoredAnswer(
                    row.purpose,
                    row.model,
                    row.request_hash,
                    dict(row.answers),
                    row.cost_usd,
                    row.served_model,
                )
                for row in rows
                if (row.model, row.request_hash) in wanted
            }

    def put(self, rows: Sequence[StoredAnswer]) -> None:
        if not rows:
            return
        with self._session_factory.begin() as session:
            session.execute(
                insert(DecisionAnswer)
                .values(
                    [
                        {
                            "id": uuid7(),
                            "purpose": row.purpose,
                            "model": row.model,
                            "served_model": row.served_model,
                            "request_hash": row.request_hash,
                            "answers": row.answers,
                            "cost_usd": row.cost_usd,
                        }
                        for row in rows
                    ]
                )
                .on_conflict_do_nothing(index_elements=["model", "request_hash"])
            )

    def spent_since(self, since: datetime) -> Decimal:
        with self._session_factory() as session:
            total = session.scalar(
                select(func.coalesce(func.sum(DecisionAnswer.cost_usd), 0)).where(
                    DecisionAnswer.created_at >= since
                )
            )
        return Decimal(str(total or 0))


@dataclass
class InMemoryDecisionStore:
    rows: dict[tuple[str, str], tuple[StoredAnswer, datetime]] = field(default_factory=dict)

    def get(self, keys: Sequence[tuple[str, str]]) -> dict[tuple[str, str], StoredAnswer]:
        return {key: self.rows[key][0] for key in keys if key in self.rows}

    def put(self, rows: Sequence[StoredAnswer]) -> None:
        for row in rows:
            self.rows.setdefault((row.model, row.request_hash), (row, utc_now()))

    def spent_since(self, since: datetime) -> Decimal:
        return sum(
            (row.cost_usd for row, created in self.rows.values() if created >= since), Decimal(0)
        )
