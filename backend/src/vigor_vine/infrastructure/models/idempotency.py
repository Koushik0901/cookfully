from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from vigor_vine.domain.common import uuid7
from vigor_vine.infrastructure.models.base import Base


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint("state IN ('processing', 'completed')", name="valid_idempotency_state"),
        CheckConstraint(
            "response_status IS NULL OR (response_status >= 100 AND response_status <= 599)",
            name="valid_idempotency_response_status",
        ),
        Index("uq_idempotency_owner_key", "owner_id", "idempotency_key", unique=True),
        Index("ix_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("owner_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
