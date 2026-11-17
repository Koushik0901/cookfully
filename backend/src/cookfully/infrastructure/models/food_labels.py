from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.infrastructure.models.base import Base


class FoodLabel(Base):
    """Decision-model labels for one USDA food, valid while ``fingerprint`` matches."""

    __tablename__ = "food_labels"

    food_reference_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("food_references.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    labels: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
