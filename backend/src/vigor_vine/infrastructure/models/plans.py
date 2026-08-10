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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vigor_vine.domain.common import uuid7
from vigor_vine.infrastructure.models.base import Base, TimestampMixin


class UserGoal(TimestampMixin, Base):
    __tablename__ = "user_goals"
    __table_args__ = (
        CheckConstraint("mode IN ('cut', 'maintain', 'bulk')", name="valid_mode"),
        CheckConstraint("maintenance_kcal > 0 AND target_kcal > 0", name="positive_calories"),
        CheckConstraint(
            "protein_g >= 0 AND carbohydrate_g >= 0 AND fat_g >= 0",
            name="nonnegative_macros",
        ),
        CheckConstraint(
            "protein_g > 0 OR carbohydrate_g > 0 OR fat_g > 0", name="some_positive_macro"
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from", name="valid_period"
        ),
        CheckConstraint("version > 0", name="positive_version"),
        ExcludeConstraint(
            ("owner_id", "="),
            (
                text("daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]')"),
                "&&",
            ),
            using="gist",
            name="nonoverlapping_owner_period",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    maintenance_kcal: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    target_kcal: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    meal_targets: Mapped[list[MealTarget]] = relationship(
        back_populates="goal", cascade="all, delete-orphan", order_by="MealTarget.position"
    )
    plans: Mapped[list[MealPlan]] = relationship(back_populates="goal")


class MealTarget(Base):
    __tablename__ = "meal_targets"
    __table_args__ = (
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint(
            "(calories_kcal IS NULL OR calories_kcal >= 0) "
            "AND (protein_g IS NULL OR protein_g >= 0) "
            "AND (carbohydrate_g IS NULL OR carbohydrate_g >= 0) "
            "AND (fat_g IS NULL OR fat_g >= 0)",
            name="nonnegative_nullable_macros",
        ),
        Index("uq_meal_targets_slot", "user_goal_id", "meal_slot", unique=True),
        Index("uq_meal_targets_position", "user_goal_id", "position", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    user_goal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_goals.id", ondelete="CASCADE"), nullable=False
    )
    meal_slot: Mapped[str] = mapped_column(String(80), nullable=False)
    calories_kcal: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    carbohydrate_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    goal: Mapped[UserGoal] = relationship(back_populates="meal_targets")


class MealPlan(TimestampMixin, Base):
    __tablename__ = "meal_plans"
    __table_args__ = (
        CheckConstraint("version > 0", name="positive_version"),
        Index("uq_meal_plans_owner_week", "owner_id", "week_start", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    goal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_goals.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    goal: Mapped[UserGoal] = relationship(back_populates="plans")
    entries: Mapped[list[MealPlanEntry]] = relationship(
        back_populates="meal_plan",
        cascade="all, delete-orphan",
        order_by=lambda: (
            MealPlanEntry.local_date,
            MealPlanEntry.meal_slot,
            MealPlanEntry.position,
        ),
    )


class MealNutritionSnapshot(Base):
    __tablename__ = "meal_nutrition_snapshots"
    __table_args__ = (
        CheckConstraint("basis_servings > 0", name="positive_servings"),
        CheckConstraint("coverage_ratio >= 0 AND coverage_ratio <= 1", name="valid_coverage"),
        CheckConstraint(
            "nutrition_state IN ('source_provided', 'estimated', 'partial', 'manual')",
            name="valid_nutrition_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="SET NULL"), index=True
    )
    estimate_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("nutrition_estimates.id", ondelete="SET NULL")
    )
    basis_servings: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    calories_kcal: Mapped[Decimal | None] = mapped_column(Numeric(20, 0))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 1))
    carbohydrate_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 1))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 1))
    nutrition_state: Mapped[str] = mapped_column(String(24), nullable=False)
    coverage_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class MealPlanEntry(TimestampMixin, Base):
    __tablename__ = "meal_plan_entries"
    __table_args__ = (
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint("servings > 0", name="positive_servings"),
        CheckConstraint("origin IN ('manual', 'suggestion', 'external')", name="valid_origin"),
        CheckConstraint("version > 0", name="positive_version"),
        Index(
            "uq_meal_plan_entries_position",
            "meal_plan_id",
            "local_date",
            "meal_slot",
            "position",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    meal_plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_slot: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="SET NULL"), index=True
    )
    recipe_title_snapshot: Mapped[str] = mapped_column(String(240), nullable=False)
    servings: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    nutrition_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("meal_nutrition_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    origin: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    meal_plan: Mapped[MealPlan] = relationship(back_populates="entries")
    nutrition_snapshot: Mapped[MealNutritionSnapshot] = relationship()
