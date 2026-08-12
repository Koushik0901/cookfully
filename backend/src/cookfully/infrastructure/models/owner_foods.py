from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base


class OwnerFood(Base):
    """Owner-scoped custom food entry with macros and optional serving data.

    Owner foods have lexical priority over USDA reference foods during matching
    so a user entering their whey protein label once reuses it on every future
    recipe import.
    """

    __tablename__ = "owner_foods"
    __table_args__ = (
        CheckConstraint("calories_kcal >= 0", name="nonnegative_calories"),
        CheckConstraint("protein_g >= 0", name="nonnegative_protein"),
        CheckConstraint("carbohydrate_g >= 0", name="nonnegative_carbs"),
        CheckConstraint("fat_g >= 0", name="nonnegative_fat"),
        CheckConstraint("basis_grams > 0", name="positive_basis"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("ix_owner_foods_owner_norm", "owner_id", "normalized_name"),
        Index("ix_owner_foods_owner_active", "owner_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(240))
    calories_kcal: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    basis_grams: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False, default=100)
    typical_serving_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    typical_serving_unit: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
