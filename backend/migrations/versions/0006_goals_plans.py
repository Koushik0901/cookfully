"""Exact owner goals, weekly plans, detached entries, and immutable nutrition snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_goals_plans"
down_revision: str | None = "0005_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gist"')
    op.create_table(
        "user_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("maintenance_kcal", sa.Numeric(20, 6), nullable=False),
        sa.Column("target_kcal", sa.Numeric(20, 6), nullable=False),
        sa.Column("protein_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("carbohydrate_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("fat_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("mode IN ('cut', 'maintain', 'bulk')", name="ck_user_goals_valid_mode"),
        sa.CheckConstraint(
            "maintenance_kcal > 0 AND target_kcal > 0", name="ck_user_goals_positive_calories"
        ),
        sa.CheckConstraint(
            "protein_g >= 0 AND carbohydrate_g >= 0 AND fat_g >= 0",
            name="ck_user_goals_nonnegative_macros",
        ),
        sa.CheckConstraint(
            "protein_g > 0 OR carbohydrate_g > 0 OR fat_g > 0",
            name="ck_user_goals_some_positive_macro",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_user_goals_valid_period",
        ),
        sa.CheckConstraint("version > 0", name="ck_user_goals_positive_version"),
        postgresql.ExcludeConstraint(
            ("owner_id", "="),
            (
                sa.text(
                    "daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]')"
                ),
                "&&",
            ),
            using="gist",
            name="x_user_goals_nonoverlapping_owner_period",
        ),
    )
    op.create_table(
        "meal_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_goal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_goals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("meal_slot", sa.String(80), nullable=False),
        sa.Column("calories_kcal", sa.Numeric(20, 6)),
        sa.Column("protein_g", sa.Numeric(20, 6)),
        sa.Column("carbohydrate_g", sa.Numeric(20, 6)),
        sa.Column("fat_g", sa.Numeric(20, 6)),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_meal_targets_nonnegative_position"),
        sa.CheckConstraint(
            "(calories_kcal IS NULL OR calories_kcal >= 0) "
            "AND (protein_g IS NULL OR protein_g >= 0) "
            "AND (carbohydrate_g IS NULL OR carbohydrate_g >= 0) "
            "AND (fat_g IS NULL OR fat_g >= 0)",
            name="ck_meal_targets_nonnegative_nullable_macros",
        ),
    )
    op.create_index(
        "uq_meal_targets_slot", "meal_targets", ["user_goal_id", "meal_slot"], unique=True
    )
    op.create_index(
        "uq_meal_targets_position", "meal_targets", ["user_goal_id", "position"], unique=True
    )
    op.create_table(
        "meal_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column(
            "goal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_goals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("version > 0", name="ck_meal_plans_positive_version"),
    )
    op.create_index(
        "uq_meal_plans_owner_week", "meal_plans", ["owner_id", "week_start"], unique=True
    )
    op.create_table(
        "meal_nutrition_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "estimate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("nutrition_estimates.id", ondelete="SET NULL"),
        ),
        sa.Column("basis_servings", sa.Numeric(12, 3), nullable=False),
        sa.Column("calories_kcal", sa.Numeric(20, 0)),
        sa.Column("protein_g", sa.Numeric(20, 1)),
        sa.Column("carbohydrate_g", sa.Numeric(20, 1)),
        sa.Column("fat_g", sa.Numeric(20, 1)),
        sa.Column("nutrition_state", sa.String(24), nullable=False),
        sa.Column("coverage_ratio", sa.Numeric(7, 6), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "basis_servings > 0", name="ck_meal_nutrition_snapshots_positive_servings"
        ),
        sa.CheckConstraint(
            "coverage_ratio >= 0 AND coverage_ratio <= 1",
            name="ck_meal_nutrition_snapshots_valid_coverage",
        ),
        sa.CheckConstraint(
            "nutrition_state IN ('source_provided', 'estimated', 'partial', 'manual')",
            name="ck_meal_nutrition_snapshots_valid_nutrition_state",
        ),
    )
    op.create_index(
        "ix_meal_nutrition_snapshots_recipe_id", "meal_nutrition_snapshots", ["recipe_id"]
    )
    op.create_table(
        "meal_plan_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "meal_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meal_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("meal_slot", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
        ),
        sa.Column("recipe_title_snapshot", sa.String(240), nullable=False),
        sa.Column("servings", sa.Numeric(12, 3), nullable=False),
        sa.Column(
            "nutrition_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meal_nutrition_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name="ck_meal_plan_entries_nonnegative_position"),
        sa.CheckConstraint("servings > 0", name="ck_meal_plan_entries_positive_servings"),
        sa.CheckConstraint(
            "origin IN ('manual', 'suggestion', 'external')",
            name="ck_meal_plan_entries_valid_origin",
        ),
        sa.CheckConstraint("version > 0", name="ck_meal_plan_entries_positive_version"),
    )
    op.create_index(
        "uq_meal_plan_entries_position",
        "meal_plan_entries",
        ["meal_plan_id", "local_date", "meal_slot", "position"],
        unique=True,
    )
    op.create_index("ix_meal_plan_entries_recipe_id", "meal_plan_entries", ["recipe_id"])


def downgrade() -> None:
    op.drop_table("meal_plan_entries")
    op.drop_table("meal_nutrition_snapshots")
    op.drop_table("meal_plans")
    op.drop_table("meal_targets")
    op.drop_table("user_goals")
