"""Durable exact-decimal suggestion runs and items."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_suggestions"
down_revision: str | None = "0007_grocery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "suggestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "meal_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meal_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("local_date", sa.Date()),
        sa.Column("meal_slot", sa.String(80)),
        sa.Column("plan_version", sa.Integer(), nullable=False),
        sa.Column("target_calories_kcal", sa.Numeric(20, 6), nullable=False),
        sa.Column("target_protein_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("target_carbohydrate_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("target_fat_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("tolerance_calories_kcal", sa.Numeric(20, 6), nullable=False),
        sa.Column("tolerance_protein_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("tolerance_carbohydrate_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("tolerance_fat_g", sa.Numeric(20, 6), nullable=False),
        sa.Column(
            "excluded_recipe_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column(
            "required_recipe_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column("max_recipe_repetitions", sa.Integer(), nullable=False),
        sa.Column("solver_version", sa.String(80), nullable=False),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("unmet_constraint_count", sa.Integer()),
        sa.Column("objective_score", sa.Numeric(20, 6)),
        sa.Column("distance_calories", sa.Numeric(20, 6)),
        sa.Column("distance_protein", sa.Numeric(20, 6)),
        sa.Column("distance_carbohydrates", sa.Numeric(20, 6)),
        sa.Column("distance_fat", sa.Numeric(20, 6)),
        sa.Column("repetition_overage", sa.Integer()),
        sa.Column("missing_required_recipes", sa.Integer()),
        sa.Column("missed_constraints", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "ordered_recipe_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column("projected_day_totals", postgresql.JSONB(), nullable=False),
        sa.Column("projected_week_total", postgresql.JSONB()),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "scope IN ('meal', 'day', 'week')", name="ck_suggestion_runs_valid_scope"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'feasible', 'infeasible', 'failed', 'expired')",
            name="ck_suggestion_runs_valid_status",
        ),
        sa.CheckConstraint("plan_version > 0", name="ck_suggestion_runs_positive_plan_version"),
        sa.CheckConstraint(
            "max_recipe_repetitions > 0", name="ck_suggestion_runs_positive_repetition_limit"
        ),
        sa.CheckConstraint("time_limit_seconds > 0", name="ck_suggestion_runs_positive_time_limit"),
    )
    op.create_table(
        "suggestion_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "suggestion_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("suggestion_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
        ),
        sa.Column("recipe_title", sa.String(240), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("meal_slot", sa.String(80), nullable=False),
        sa.Column("servings", sa.Numeric(12, 3), nullable=False),
        sa.Column("calories_kcal", sa.Numeric(20, 6), nullable=False),
        sa.Column("protein_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("carbohydrate_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("fat_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("nutrition_state", sa.String(24), nullable=False),
        sa.Column("coverage_ratio", sa.Numeric(7, 6), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "accepted_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meal_plan_entries.id", ondelete="SET NULL"),
        ),
        sa.CheckConstraint("servings > 0", name="ck_suggestion_items_positive_servings"),
        sa.CheckConstraint("position >= 0", name="ck_suggestion_items_nonnegative_position"),
    )
    op.create_index(
        "uq_suggestion_items_position",
        "suggestion_items",
        ["suggestion_run_id", "position"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("suggestion_items")
    op.drop_table("suggestion_runs")
