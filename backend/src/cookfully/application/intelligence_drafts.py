from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, utc_now, uuid7
from cookfully.infrastructure.models.intelligence import IntelligenceDraftRecord


class IntelligenceDraftService:
    def __init__(
        self, session_factory: sessionmaker[Session], *, ttl: timedelta = timedelta(minutes=10)
    ) -> None:
        self._session_factory = session_factory
        self._ttl = ttl

    def create(
        self,
        owner_id: UUID,
        *,
        operation: str,
        payload: dict[str, Any],
        confidence: float | None,
    ) -> IntelligenceDraftRecord:
        now = utc_now()
        with self._session_factory.begin() as session:
            record = IntelligenceDraftRecord(
                id=uuid7(),
                owner_id=owner_id,
                operation=operation,
                status="review",
                confidence=confidence,
                payload=payload,
                created_at=now,
                expires_at=now + self._ttl,
            )
            session.add(record)
            session.flush()
            return record

    def create_pending(
        self,
        owner_id: UUID,
        *,
        operation: str,
        payload: dict[str, Any],
    ) -> IntelligenceDraftRecord:
        now = utc_now()
        with self._session_factory.begin() as session:
            record = IntelligenceDraftRecord(
                id=uuid7(),
                owner_id=owner_id,
                operation=operation,
                status="queued",
                payload=payload,
                created_at=now,
                expires_at=now + self._ttl,
            )
            session.add(record)
            session.flush()
            return record

    def complete_pending(
        self,
        draft_id: UUID,
        *,
        status: str,
        payload: dict[str, Any],
        confidence: float | None,
    ) -> None:
        with self._session_factory.begin() as session:
            record = session.get(IntelligenceDraftRecord, draft_id, with_for_update=True)
            if record is None:
                raise DomainError(
                    "intelligence_draft_not_found", "The intelligence draft was not found.", 404
                )
            record.status = status
            record.payload = payload
            record.confidence = confidence

    def mark_processing(self, draft_id: UUID) -> None:
        with self._session_factory.begin() as session:
            record = session.get(IntelligenceDraftRecord, draft_id, with_for_update=True)
            if record is not None and record.status == "queued":
                record.status = "processing"

    def fail_pending(self, draft_id: UUID, *, code: str, message: str) -> None:
        with self._session_factory.begin() as session:
            record = session.get(IntelligenceDraftRecord, draft_id, with_for_update=True)
            if record is None:
                return
            record.status = "failed"
            record.failure_code = code
            record.failure_message = message

    def get(
        self, owner_id: UUID, draft_id: UUID, *, for_update: bool = False
    ) -> IntelligenceDraftRecord:
        with self._session_factory() as session:
            query = select(IntelligenceDraftRecord).where(
                IntelligenceDraftRecord.id == draft_id,
                IntelligenceDraftRecord.owner_id == owner_id,
            )
            if for_update:
                query = query.with_for_update()
            record = session.scalar(query)
            if record is None:
                raise DomainError(
                    "intelligence_draft_not_found", "The intelligence draft was not found.", 404
                )
            if record.expires_at <= utc_now() and record.status in {
                "queued",
                "processing",
                "review",
            }:
                raise DomainError(
                    "intelligence_draft_expired", "This proposal has expired. Try again.", 410
                )
            return record

    def mark_executed(self, owner_id: UUID, draft_id: UUID) -> None:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(IntelligenceDraftRecord)
                .where(
                    IntelligenceDraftRecord.id == draft_id,
                    IntelligenceDraftRecord.owner_id == owner_id,
                )
                .with_for_update()
            )
            if record is None:
                raise DomainError(
                    "intelligence_draft_not_found", "The intelligence draft was not found.", 404
                )
            if record.status != "review":
                raise DomainError(
                    "intelligence_draft_already_used", "This proposal was already used.", 409
                )
            if record.expires_at <= utc_now():
                raise DomainError(
                    "intelligence_draft_expired", "This proposal has expired. Try again.", 410
                )
            record.status = "executed"
            record.executed_at = utc_now()

    def expire(self, *, now: datetime | None = None) -> int:
        checked_at = now or utc_now()
        with self._session_factory.begin() as session:
            records = list(
                session.scalars(
                    select(IntelligenceDraftRecord).where(
                        IntelligenceDraftRecord.status == "review",
                        IntelligenceDraftRecord.expires_at <= checked_at,
                    )
                )
            )
            for record in records:
                record.status = "expired"
            return len(records)
