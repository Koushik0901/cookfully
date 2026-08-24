from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base, TimestampMixin


class PantryItem(TimestampMixin, Base):
    __tablename__ = "pantry_items"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="nonnegative_quantity"),
        CheckConstraint(
            "match_status IN ('unmatched', 'proposed', 'matched', 'manual')",
            name="valid_match_status",
        ),
        CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name="valid_match_confidence",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "expiry_source IN ('auto', 'label', 'manual')",
            name="valid_expiry_source",
        ),
        Index("ix_pantry_items_owner_name", "owner_id", "normalized_food_name"),
        Index("ix_pantry_items_owner_expires_on", "owner_id", "expires_on"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_food_name: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date)
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiry_source: Mapped[str | None] = mapped_column(String(10), nullable=True)
    food_reference_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("food_references.id", ondelete="SET NULL")
    )
    match_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unmatched")
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    deductions: Mapped[list[PantryDeduction]] = relationship(
        back_populates="pantry_item", cascade="all, delete-orphan"
    )


class PantryDeduction(TimestampMixin, Base):
    __tablename__ = "pantry_deductions"
    __table_args__ = (
        CheckConstraint("pantry_quantity > 0", name="positive_pantry_quantity"),
        CheckConstraint("grocery_quantity > 0", name="positive_grocery_quantity"),
        CheckConstraint("status IN ('applied', 'reversed')", name="valid_status"),
        CheckConstraint("pantry_version_after > 0", name="positive_pantry_version"),
        CheckConstraint("grocery_version_after > 0", name="positive_grocery_version"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "(status = 'applied' AND reversed_at IS NULL) OR "
            "(status = 'reversed' AND reversed_at IS NOT NULL)",
            name="reversal_state_consistent",
        ),
        Index("ix_pantry_deductions_grocery", "grocery_item_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    pantry_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pantry_items.id", ondelete="CASCADE"), nullable=False
    )
    grocery_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("grocery_items.id", ondelete="CASCADE"), nullable=False
    )
    pantry_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    pantry_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    grocery_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    grocery_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    assumption: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="applied")
    pantry_version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    grocery_version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    pantry_item: Mapped[PantryItem] = relationship(back_populates="deductions")
