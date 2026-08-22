from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base, TimestampMixin


class PublicVector(Vector):
    """Keep the extension type resolvable from isolated test schemas."""

    def get_col_spec(self, **kw: Any) -> str:
        if self.dim is None:
            return "public.VECTOR"
        return f"public.VECTOR({self.dim})"


class FoodSemanticIndex(TimestampMixin, Base):
    __tablename__ = "food_semantic_index"
    __table_args__ = (
        CheckConstraint(
            "((food_reference_id IS NOT NULL)::int + (owner_food_id IS NOT NULL)::int) = 1",
            name="semantic_index_single_source",
        ),
        Index("ix_food_semantic_index_active_version", "model_name", "model_version"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    food_reference_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("food_references.id", ondelete="CASCADE")
    )
    owner_food_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_foods.id", ondelete="CASCADE")
    )
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dimensions: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    embedding_vector: Mapped[list[float] | None] = mapped_column(PublicVector(384))
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source_release_id: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FoodMatchMemory(TimestampMixin, Base):
    __tablename__ = "food_match_memories"
    __table_args__ = (
        CheckConstraint(
            "((food_reference_id IS NOT NULL)::int + (owner_food_id IS NOT NULL)::int) = 1",
            name="food_match_memory_single_source",
        ),
        Index(
            "uq_food_match_memories_owner_signature",
            "owner_id",
            "signature_hash",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False
    )
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    food_reference_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("food_references.id", ondelete="RESTRICT")
    )
    owner_food_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_foods.id", ondelete="RESTRICT")
    )
    source_release_id: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    use_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
