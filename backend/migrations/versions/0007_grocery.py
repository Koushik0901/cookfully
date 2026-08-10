"""Grocery lists, exact-decimal items, and detached source provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_grocery"
down_revision: str | None = "0006_goals_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grocery_lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "meal_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meal_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_plan_version", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('current', 'dirty', 'generating', 'failed')",
            name="ck_grocery_lists_valid_status",
        ),
        sa.CheckConstraint(
            "source_plan_version > 0", name="ck_grocery_lists_positive_source_plan_version"
        ),
        sa.CheckConstraint("version > 0", name="ck_grocery_lists_positive_version"),
    )
    op.create_index("uq_grocery_lists_meal_plan", "grocery_lists", ["meal_plan_id"], unique=True)
    op.create_table(
        "grocery_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "grocery_list_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("grocery_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("normalized_food_name", sa.String(240), nullable=False),
        sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6)),
        sa.Column("unit_code", sa.String(80)),
        sa.Column("unit_text", sa.String(120)),
        sa.Column("aggregation_key", sa.String(400)),
        sa.Column("origin", sa.String(24), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False),
        sa.Column("manual_quantity", sa.Boolean(), nullable=False),
        sa.Column("manual_name", sa.Boolean(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity >= 0", name="ck_grocery_items_nonnegative_quantity"
        ),
        sa.CheckConstraint(
            "origin IN ('generated', 'manual')", name="ck_grocery_items_valid_origin"
        ),
        sa.CheckConstraint("position >= 0", name="ck_grocery_items_nonnegative_position"),
        sa.CheckConstraint("version > 0", name="ck_grocery_items_positive_version"),
    )
    op.create_index(
        "uq_grocery_items_position", "grocery_items", ["grocery_list_id", "position"], unique=True
    )
    op.create_index(
        "ix_grocery_items_aggregation_key", "grocery_items", ["grocery_list_id", "aggregation_key"]
    )
    op.create_table(
        "grocery_item_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "grocery_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("grocery_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("meal_plan_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ingredient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingredients.id", ondelete="SET NULL"),
        ),
        sa.Column("quantity_contribution", sa.Numeric(20, 6)),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "quantity_contribution IS NULL OR quantity_contribution >= 0",
            name="ck_grocery_item_sources_nonnegative_quantity_contribution",
        ),
    )
    op.create_index(
        "uq_grocery_item_sources_origin",
        "grocery_item_sources",
        ["grocery_item_id", "meal_plan_entry_id", "ingredient_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_table("grocery_item_sources")
    op.drop_table("grocery_items")
    op.drop_table("grocery_lists")
