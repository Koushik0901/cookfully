"""Ingredient matching, immutable nutrition estimates, and typed corrections."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_nutrition"
down_revision: str | None = "0004_reference_foods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingredient_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ingredient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "food_reference_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("food_references.id", ondelete="RESTRICT"),
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("match_method", sa.String(32), nullable=False),
        sa.Column("match_score", sa.Numeric(7, 6)),
        sa.Column("grams_min", sa.Numeric(20, 6)),
        sa.Column("grams_max", sa.Numeric(20, 6)),
        sa.Column("conversion_method", sa.String(32)),
        sa.Column("density_g_per_ml", sa.Numeric(20, 6)),
        sa.Column("assumption_text", sa.Text()),
        sa.Column("source_release_id", sa.String(120)),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 1)",
            name="valid_match_score",
        ),
        sa.CheckConstraint(
            "grams_min IS NULL OR grams_min >= 0",
            name="nonnegative_grams_min",
        ),
        sa.CheckConstraint(
            "grams_max IS NULL OR grams_max >= grams_min",
            name="valid_grams_range",
        ),
        sa.CheckConstraint(
            "density_g_per_ml IS NULL OR density_g_per_ml > 0",
            name="positive_density",
        ),
    )
    op.create_index(
        "uq_ingredient_matches_active",
        "ingredient_matches",
        ["ingredient_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_table(
        "nutrition_estimates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("basis_servings", sa.Numeric(12, 3), nullable=False),
        sa.Column("calories_kcal", sa.Numeric(20, 6)),
        sa.Column("protein_g", sa.Numeric(20, 6)),
        sa.Column("carbohydrate_g", sa.Numeric(20, 6)),
        sa.Column("fat_g", sa.Numeric(20, 6)),
        sa.Column("fiber_g", sa.Numeric(20, 6)),
        sa.Column("sodium_mg", sa.Numeric(20, 6)),
        sa.Column("coverage_ratio", sa.Numeric(7, 6), nullable=False),
        sa.Column("source_label", sa.String(240)),
        sa.Column("source_url", sa.Text()),
        sa.Column("assumptions_summary", sa.Text()),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("pipeline_version", sa.String(80), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("nutrition_estimates.id", ondelete="SET NULL"),
        ),
        sa.CheckConstraint("basis_servings > 0", name="positive_basis_servings"),
        sa.CheckConstraint(
            "coverage_ratio >= 0 AND coverage_ratio <= 1",
            name="valid_coverage_ratio",
        ),
    )
    op.create_index(
        "ix_nutrition_estimates_recipe_calculated",
        "nutrition_estimates",
        ["recipe_id", "calculated_at"],
    )
    op.create_index(
        "uq_nutrition_estimates_input_pipeline",
        "nutrition_estimates",
        ["recipe_id", "input_hash", "pipeline_version"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_recipes_active_estimate_id_nutrition_estimates",
        "recipes",
        "nutrition_estimates",
        ["active_estimate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "nutrition_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ingredient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
        ),
        sa.Column("field", sa.String(60), nullable=False),
        sa.Column("decimal_value", sa.Numeric(20, 6)),
        sa.Column("text_value", sa.Text()),
        sa.Column("reference_id_value", postgresql.UUID(as_uuid=True)),
        sa.Column("reason", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reset_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "((decimal_value IS NOT NULL)::int + (text_value IS NOT NULL)::int + "
            "(reference_id_value IS NOT NULL)::int) = 1",
            name="exactly_one_typed_value",
        ),
    )
    op.create_index(
        "uq_nutrition_corrections_active",
        "nutrition_corrections",
        ["recipe_id", "ingredient_id", "field"],
        unique=True,
        postgresql_where=sa.text("active"),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_table("nutrition_corrections")
    op.drop_constraint(
        "fk_recipes_active_estimate_id_nutrition_estimates", "recipes", type_="foreignkey"
    )
    op.drop_table("nutrition_estimates")
    op.drop_table("ingredient_matches")
