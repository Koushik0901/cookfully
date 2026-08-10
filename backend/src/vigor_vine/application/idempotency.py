from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.domain.common import DomainError, utc_now
from vigor_vine.infrastructure.models.idempotency import IdempotencyRecord


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    replay: bool
    resource_id: UUID | None = None
    job_id: UUID | None = None
    response_status: int | None = None
    response_body: dict[str, Any] | None = None


class IdempotencyService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        retention: timedelta = timedelta(hours=24),
    ) -> None:
        self._session_factory = session_factory
        self._retention = retention

    def begin(
        self,
        *,
        owner_id: UUID,
        key: str,
        operation: str,
        payload: object,
        now: datetime | None = None,
    ) -> IdempotencyDecision:
        checked_at = now or utc_now()
        request_hash = self.request_hash(operation, payload)
        try:
            with self._session_factory.begin() as session:
                existing = session.scalar(
                    select(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.owner_id == owner_id,
                        IdempotencyRecord.idempotency_key == key,
                    )
                    .with_for_update()
                )
                if existing is not None:
                    if existing.operation != operation or existing.request_hash != request_hash:
                        raise DomainError(
                            "idempotency_conflict",
                            "Idempotency key was already used for a different request.",
                            409,
                        )
                    if existing.state == "completed":
                        return IdempotencyDecision(
                            True,
                            existing.resource_id,
                            existing.job_id,
                            existing.response_status,
                            existing.response_body,
                        )
                    if existing.expires_at > checked_at:
                        raise DomainError(
                            "idempotency_in_progress",
                            "The original request is still being processed.",
                            409,
                        )
                    existing.state = "processing"
                    existing.created_at = checked_at
                    existing.completed_at = None
                    existing.expires_at = checked_at + self._retention
                    existing.response_status = None
                    existing.resource_id = None
                    existing.job_id = None
                    existing.response_body = None
                    return IdempotencyDecision(False)
                session.add(
                    IdempotencyRecord(
                        owner_id=owner_id,
                        idempotency_key=key,
                        operation=operation,
                        request_hash=request_hash,
                        state="processing",
                        created_at=checked_at,
                        expires_at=checked_at + self._retention,
                    )
                )
            return IdempotencyDecision(False)
        except IntegrityError:
            # A concurrent request won the unique-key race; inspect its durable state.
            return self.begin(
                owner_id=owner_id,
                key=key,
                operation=operation,
                payload=payload,
                now=checked_at,
            )

    def complete(
        self,
        *,
        owner_id: UUID,
        key: str,
        response_status: int,
        resource_id: UUID | None = None,
        job_id: UUID | None = None,
        response_body: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> None:
        completed_at = now or utc_now()
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(IdempotencyRecord)
                .where(
                    IdempotencyRecord.owner_id == owner_id,
                    IdempotencyRecord.idempotency_key == key,
                )
                .with_for_update()
            )
            if record is None:
                raise DomainError(
                    "idempotency_record_missing", "Idempotency reservation was lost.", 500
                )
            record.state = "completed"
            record.response_status = response_status
            record.resource_id = resource_id
            record.job_id = job_id
            record.response_body = response_body
            record.completed_at = completed_at

    def abort(self, *, owner_id: UUID, key: str) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                delete(IdempotencyRecord).where(
                    IdempotencyRecord.owner_id == owner_id,
                    IdempotencyRecord.idempotency_key == key,
                    IdempotencyRecord.state == "processing",
                )
            )

    def delete_expired(self, *, now: datetime | None = None) -> int:
        checked_at = now or utc_now()
        with self._session_factory.begin() as session:
            expired_ids = list(
                session.scalars(
                    select(IdempotencyRecord.id).where(IdempotencyRecord.expires_at <= checked_at)
                )
            )
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.expires_at <= checked_at)
            )
            return len(expired_ids)

    @staticmethod
    def request_hash(operation: str, payload: object) -> str:
        canonical = json.dumps(
            {"operation": operation, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()
