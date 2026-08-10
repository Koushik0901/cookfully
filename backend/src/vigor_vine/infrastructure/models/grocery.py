from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from vigor_vine.domain.common import uuid7
from vigor_vine.infrastructure.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from vigor_vine.infrastructure.models.plans import MealPlan


class GroceryList(TimestampMixin, Base):
    __tablename__ = "grocery_lists"
    __table_args__ = (
        CheckConstraint(
            "status IN ('current', 'dirty', 'generating', 'failed')", name="valid_status"
        ),
        CheckConstraint("source_plan_version > 0", name="positive_source_plan_version"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("uq_grocery_lists_meal_plan", "meal_plan_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    meal_plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="dirty")
    source_plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    meal_plan: Mapped[MealPlan] = relationship(back_populates="grocery_list")
    items: Mapped[list[GroceryItem]] = relationship(
        back_populates="grocery_list",
        cascade="all, delete-orphan",
        order_by="GroceryItem.position",
    )


class GroceryItem(TimestampMixin, Base):
    __tablename__ = "grocery_items"
    __table_args__ = (
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="nonnegative_quantity"),
        CheckConstraint("origin IN ('generated', 'manual')", name="valid_origin"),
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("uq_grocery_items_position", "grocery_list_id", "position", unique=True),
        Index("ix_grocery_items_aggregation_key", "grocery_list_id", "aggregation_key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    grocery_list_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("grocery_lists.id", ondelete="CASCADE"), nullable=False
    )
    normalized_food_name: Mapped[str] = mapped_column(String(240), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    unit_code: Mapped[str | None] = mapped_column(String(80))
    unit_text: Mapped[str | None] = mapped_column(String(120))
    aggregation_key: Mapped[str | None] = mapped_column(String(400))
    origin: Mapped[str] = mapped_column(String(24), nullable=False)
    checked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manual_quantity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manual_name: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    grocery_list: Mapped[GroceryList] = relationship(back_populates="items")
    sources: Mapped[list[GroceryItemSource]] = relationship(
        back_populates="grocery_item", cascade="all, delete-orphan"
    )


class GroceryItemSource(Base):
    __tablename__ = "grocery_item_sources"
    __table_args__ = (
        CheckConstraint(
            "quantity_contribution IS NULL OR quantity_contribution >= 0",
            name="nonnegative_quantity_contribution",
        ),
        Index(
            "uq_grocery_item_sources_origin",
            "grocery_item_id",
            "meal_plan_entry_id",
            "ingredient_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    grocery_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("grocery_items.id", ondelete="CASCADE"), nullable=False
    )
    meal_plan_entry_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    ingredient_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="SET NULL")
    )
    quantity_contribution: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    original_text: Mapped[str] = mapped_column(Text, nullable=False)

    grocery_item: Mapped[GroceryItem] = relationship(back_populates="sources")
