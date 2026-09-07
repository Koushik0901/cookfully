"""Persist planned cooking progress and optional leftovers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_durable_cooking_sessions"
down_revision: str | None = "0030_health_context_and_goal_nutrients"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_nutrition_state_constraint() -> None:
    """Drop the pre-0031 check regardless of naming-convention hash suffixes."""

    bind = op.get_bind()
    name = bind.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'meal_nutrition_snapshots'::regclass "
            "AND contype = 'c' "
            "AND pg_get_constraintdef(oid) LIKE '%nutrition_state%'"
        )
    ).scalar_one_or_none()
    if name:
        op.drop_constraint(op.f(name), "meal_nutrition_snapshots", type_="check")


def upgrade() -> None:
    _drop_nutrition_state_constraint()
    op.create_check_constraint(
        op.f("ck_meal_nutrition_snapshots_valid_nutrition_state"),
        "meal_nutrition_snapshots",
        "nutrition_state IN ('unavailable', 'source_provided', 'estimated', 'partial', 'manual')",
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("cooking_status", sa.String(16), nullable=False, server_default="planned"),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("cooking_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column(
            "checked_ingredient_positions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("cooking_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("cooked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("prepared_servings", sa.Numeric(12, 3), nullable=True),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("leftover_servings", sa.Numeric(12, 3), nullable=True),
    )
    op.add_column(
        "meal_plan_entries",
        sa.Column("leftovers_expires_on", sa.Date(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_meal_plan_entries_valid_cooking_status"),
        "meal_plan_entries",
        "cooking_status IN ('planned', 'cooking', 'cooked')",
    )
    op.create_check_constraint(
        op.f("ck_meal_plan_entries_nonnegative_cooking_step"),
        "meal_plan_entries",
        "cooking_step >= 0",
    )
    op.create_check_constraint(
        op.f("ck_meal_plan_entries_positive_prepared_servings"),
        "meal_plan_entries",
        "prepared_servings IS NULL OR prepared_servings > 0",
    )
    op.create_check_constraint(
        op.f("ck_meal_plan_entries_nonnegative_leftover_servings"),
        "meal_plan_entries",
        "leftover_servings IS NULL OR leftover_servings >= 0",
    )
    op.create_check_constraint(
        op.f("ck_meal_plan_entries_leftovers_within_prepared_servings"),
        "meal_plan_entries",
        "leftover_servings IS NULL OR prepared_servings IS NULL "
        "OR leftover_servings <= prepared_servings",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_meal_plan_entries_leftovers_within_prepared_servings"),
        "meal_plan_entries",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_meal_plan_entries_nonnegative_leftover_servings"),
        "meal_plan_entries",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_meal_plan_entries_positive_prepared_servings"),
        "meal_plan_entries",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_meal_plan_entries_nonnegative_cooking_step"),
        "meal_plan_entries",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_meal_plan_entries_valid_cooking_status"),
        "meal_plan_entries",
        type_="check",
    )
    op.drop_column("meal_plan_entries", "leftovers_expires_on")
    op.drop_column("meal_plan_entries", "leftover_servings")
    op.drop_column("meal_plan_entries", "prepared_servings")
    op.drop_column("meal_plan_entries", "cooked_at")
    op.drop_column("meal_plan_entries", "cooking_started_at")
    op.drop_column("meal_plan_entries", "checked_ingredient_positions")
    op.drop_column("meal_plan_entries", "cooking_step")
    op.drop_column("meal_plan_entries", "cooking_status")
    _drop_nutrition_state_constraint()
    op.create_check_constraint(
        op.f("ck_meal_nutrition_snapshots_valid_nutrition_state"),
        "meal_nutrition_snapshots",
        "nutrition_state IN ('source_provided', 'estimated', 'partial', 'manual')",
    )
