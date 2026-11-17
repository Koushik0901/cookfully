from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base


class DecisionAnswer(Base):
    """One model's validated answer to one decision request, plus what it cost.

    Doubles as the cache (unique on model + request hash) and the spend ledger.
    """

    __tablename__ = "decision_answers"
    __table_args__ = (
        Index("uq_decision_answers_request", "model", "request_hash", unique=True),
        Index("ix_decision_answers_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    served_model: Mapped[str | None] = mapped_column(String(160))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 9), nullable=False, default=Decimal(0), server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
