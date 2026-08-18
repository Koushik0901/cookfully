from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base, TimestampMixin


class IngredientMatch(TimestampMixin, Base):
    __tablename__ = "ingredient_matches"
    __table_args__ = (
        CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 1)",
            name="valid_match_score",
        ),
        CheckConstraint("grams_min IS NULL OR grams_min >= 0", name="nonnegative_grams_min"),
        CheckConstraint("grams_max IS NULL OR grams_max >= grams_min", name="valid_grams_range"),
        CheckConstraint(
            "density_g_per_ml IS NULL OR density_g_per_ml > 0", name="positive_density"
        ),
        CheckConstraint(
            "(food_reference_id IS NULL) OR (owner_food_id IS NULL)",
            name="single_food_source",
        ),
        Index(
            "uq_ingredient_matches_active",
            "ingredient_id",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    ingredient_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=False
    )
    food_reference_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("food_references.id", ondelete="RESTRICT")
    )
    owner_food_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_foods.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    match_method: Mapped[str] = mapped_column(String(32), nullable=False)
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    grams_min: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    grams_max: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    conversion_method: Mapped[str | None] = mapped_column(String(32))
    density_g_per_ml: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    assumption_text: Mapped[str | None] = mapped_column(Text)
    source_release_id: Mapped[str | None] = mapped_column(String(120))
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolution_kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="confirmed", server_default="confirmed"
    )
    candidate_evidence: Mapped[list[dict[str, object]] | None] = mapped_column(JSON)
    provisional_macros: Mapped[dict[str, object] | None] = mapped_column(JSON)


class NutritionEstimate(Base):
    __tablename__ = "nutrition_estimates"
    __table_args__ = (
        CheckConstraint("basis_servings > 0", name="positive_basis_servings"),
        CheckConstraint("coverage_ratio >= 0 AND coverage_ratio <= 1", name="valid_coverage_ratio"),
        Index("ix_nutrition_estimates_recipe_calculated", "recipe_id", "calculated_at"),
        Index(
            "uq_nutrition_estimates_input_pipeline",
            "recipe_id",
            "input_hash",
            "pipeline_version",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    basis_servings: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    calories_kcal: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    carbohydrate_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    sodium_mg: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    potassium_mg: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    calcium_mg: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    iron_mg: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    magnesium_mg: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    vitamin_c_mg: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    vitamin_d_ug: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    vitamin_b12_ug: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    micronutrient_mapping_version: Mapped[str | None] = mapped_column(String(80))
    coverage_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(240))
    source_url: Mapped[str | None] = mapped_column(Text)
    assumptions_summary: Mapped[str | None] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("nutrition_estimates.id", ondelete="SET NULL")
    )


class NutritionCorrection(TimestampMixin, Base):
    __tablename__ = "nutrition_corrections"
    __table_args__ = (
        CheckConstraint(
            "((decimal_value IS NOT NULL)::int + (text_value IS NOT NULL)::int + "
            "(reference_id_value IS NOT NULL)::int) = 1",
            name="exactly_one_typed_value",
        ),
        Index(
            "uq_nutrition_corrections_active",
            "recipe_id",
            "ingredient_id",
            "field",
            unique=True,
            postgresql_where=text("active"),
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE")
    )
    field: Mapped[str] = mapped_column(String(60), nullable=False)
    decimal_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    reference_id_value: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
