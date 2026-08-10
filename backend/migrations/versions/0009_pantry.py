"""Pantry, reversible deductions, and typed P6 micronutrients."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_pantry"
down_revision: str | None = "0008_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MICRONUTRIENT_COLUMNS = (
    "dietary_fiber_g",
    "sodium_mg",
    "potassium_mg",
    "calcium_mg",
    "iron_mg",
    "magnesium_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
    "vitamin_b12_ug",
)


def upgrade() -> None:
    op.add_column("food_nutrients", sa.Column("canonical_key", sa.String(40)))
    op.add_column("food_nutrients", sa.Column("mapping_version", sa.String(80)))
    op.add_column(
        "food_nutrients",
        sa.Column("explicit_zero", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_food_nutrients_canonical_key", "food_nutrients", ["canonical_key"])

    for name in MICRONUTRIENT_COLUMNS:
        if name not in {"dietary_fiber_g", "sodium_mg"}:
            op.add_column("nutrition_estimates", sa.Column(name, sa.Numeric(20, 6)))
        op.add_column("meal_nutrition_snapshots", sa.Column(name, sa.Numeric(20, 6)))
    op.add_column("nutrition_estimates", sa.Column("micronutrient_mapping_version", sa.String(80)))

    op.create_table(
        "pantry_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("normalized_food_name", sa.String(240), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit_code", sa.String(20), nullable=False),
        sa.Column(
            "food_reference_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("food_references.id", ondelete="SET NULL"),
        ),
        sa.Column("match_status", sa.String(24), nullable=False),
        sa.Column("match_confidence", sa.Numeric(7, 6)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity >= 0", name="ck_pantry_items_nonnegative_quantity"),
        sa.CheckConstraint(
            "match_status IN ('unmatched', 'proposed', 'matched', 'manual')",
            name="ck_pantry_items_valid_match_status",
        ),
        sa.CheckConstraint(
            "match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)",
            name="ck_pantry_items_valid_match_confidence",
        ),
        sa.CheckConstraint("version > 0", name="ck_pantry_items_positive_version"),
    )
    op.create_index(
        "ix_pantry_items_owner_name", "pantry_items", ["owner_id", "normalized_food_name"]
    )
    op.create_table(
        "pantry_deductions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "pantry_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pantry_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grocery_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("grocery_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pantry_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("pantry_unit", sa.String(20), nullable=False),
        sa.Column("grocery_quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("grocery_unit", sa.String(20), nullable=False),
        sa.Column("assumption", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("pantry_version_after", sa.Integer(), nullable=False),
        sa.Column("grocery_version_after", sa.Integer(), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "pantry_quantity > 0", name="ck_pantry_deductions_positive_pantry_quantity"
        ),
        sa.CheckConstraint(
            "grocery_quantity > 0", name="ck_pantry_deductions_positive_grocery_quantity"
        ),
        sa.CheckConstraint(
            "status IN ('applied', 'reversed')", name="ck_pantry_deductions_valid_status"
        ),
        sa.CheckConstraint(
            "pantry_version_after > 0", name="ck_pantry_deductions_positive_pantry_version"
        ),
        sa.CheckConstraint(
            "grocery_version_after > 0", name="ck_pantry_deductions_positive_grocery_version"
        ),
        sa.CheckConstraint("version > 0", name="ck_pantry_deductions_positive_version"),
        sa.CheckConstraint(
            "(status = 'applied' AND reversed_at IS NULL) OR "
            "(status = 'reversed' AND reversed_at IS NOT NULL)",
            name="ck_pantry_deductions_reversal_state_consistent",
        ),
    )
    op.create_index(
        "ix_pantry_deductions_grocery", "pantry_deductions", ["grocery_item_id", "status"]
    )


def downgrade() -> None:
    op.drop_table("pantry_deductions")
    op.drop_table("pantry_items")
    op.drop_column("nutrition_estimates", "micronutrient_mapping_version")
    for name in reversed(MICRONUTRIENT_COLUMNS):
        op.drop_column("meal_nutrition_snapshots", name)
        if name not in {"dietary_fiber_g", "sodium_mg"}:
            op.drop_column("nutrition_estimates", name)
    op.drop_index("ix_food_nutrients_canonical_key", table_name="food_nutrients")
    op.drop_column("food_nutrients", "explicit_zero")
    op.drop_column("food_nutrients", "mapping_version")
    op.drop_column("food_nutrients", "canonical_key")
