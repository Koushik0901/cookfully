from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vigor_vine.domain.common import uuid7
from vigor_vine.infrastructure.models.base import Base, TimestampMixin


class SuggestionRun(TimestampMixin, Base):
    __tablename__ = "suggestion_runs"
    __table_args__ = (
        CheckConstraint("scope IN ('meal', 'day', 'week')", name="valid_scope"),
        CheckConstraint(
            "status IN ('queued', 'running', 'feasible', 'infeasible', 'failed', 'expired')",
            name="valid_status",
        ),
        CheckConstraint("plan_version > 0", name="positive_plan_version"),
        CheckConstraint("max_recipe_repetitions > 0", name="positive_repetition_limit"),
        CheckConstraint("time_limit_seconds > 0", name="positive_time_limit"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False
    )
    meal_plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("processing_jobs.id", ondelete="SET NULL"), unique=True
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    local_date: Mapped[date | None] = mapped_column(Date)
    meal_slot: Mapped[str | None] = mapped_column(String(80))
    plan_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_calories_kcal: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    target_protein_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    target_carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    target_fat_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    tolerance_calories_kcal: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    tolerance_protein_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    tolerance_carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    tolerance_fat_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    excluded_recipe_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    required_recipe_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    max_recipe_repetitions: Mapped[int] = mapped_column(Integer, nullable=False)
    solver_version: Mapped[str] = mapped_column(String(80), nullable=False)
    time_limit_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    unmet_constraint_count: Mapped[int | None] = mapped_column(Integer)
    objective_score: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    distance_calories: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    distance_protein: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    distance_carbohydrates: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    distance_fat: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    repetition_overage: Mapped[int | None] = mapped_column(Integer)
    missing_required_recipes: Mapped[int | None] = mapped_column(Integer)
    missed_constraints: Mapped[list[str]] = mapped_column(
        ARRAY(Text()), nullable=False, default=list
    )
    ordered_recipe_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False, default=list
    )
    projected_day_totals: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    projected_week_total: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list[SuggestionItem]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="SuggestionItem.position"
    )


class SuggestionItem(Base):
    __tablename__ = "suggestion_items"
    __table_args__ = (
        CheckConstraint("servings > 0", name="positive_servings"),
        CheckConstraint("position >= 0", name="nonnegative_position"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    suggestion_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("suggestion_runs.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="SET NULL")
    )
    recipe_title: Mapped[str] = mapped_column(String(240), nullable=False)
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    meal_slot: Mapped[str] = mapped_column(String(80), nullable=False)
    servings: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    calories_kcal: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    carbohydrate_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    nutrition_state: Mapped[str] = mapped_column(String(24), nullable=False)
    coverage_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_entry_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("meal_plan_entries.id", ondelete="SET NULL")
    )
    run: Mapped[SuggestionRun] = relationship(back_populates="items")
