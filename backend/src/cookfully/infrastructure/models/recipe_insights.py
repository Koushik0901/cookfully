from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base


class RecipeInsight(Base):
    """A decision-model result about a recipe, valid while ``fingerprint`` still matches.

    ``fingerprint`` hashes everything the result depends on (the recipe's input, owner settings such
    as the avoid list, and the prompt version), so a stale row is detected without bookkeeping.
    """

    __tablename__ = "recipe_insights"
    __table_args__ = (Index("uq_recipe_insights_kind", "recipe_id", "kind", unique=True),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
