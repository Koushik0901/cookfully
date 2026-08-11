"""Branded food import support, owner-created foods, and polymorphic ingredient matching."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_branded_user_foods"
down_revision: str | None = "0009_pantry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "food_references",
        sa.Column("serving_size_g", sa.Numeric(20, 6)),
    )
    op.add_column(
        "food_references",
        sa.Column("serving_unit", sa.String(20)),
    )

    op.create_table(
        "owner_foods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("brand", sa.String(240)),
        sa.Column("calories_kcal", sa.Numeric(20, 6), nullable=False),
        sa.Column("protein_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("carbohydrate_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("fat_g", sa.Numeric(20, 6), nullable=False),
        sa.Column("basis_grams", sa.Numeric(20, 6), nullable=False, server_default="100"),
        sa.Column("typical_serving_g", sa.Numeric(20, 6)),
        sa.Column("typical_serving_unit", sa.String(20)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("calories_kcal >= 0", name="nonnegative_calories"),
        sa.CheckConstraint("protein_g >= 0", name="nonnegative_protein"),
        sa.CheckConstraint("carbohydrate_g >= 0", name="nonnegative_carbs"),
        sa.CheckConstraint("fat_g >= 0", name="nonnegative_fat"),
        sa.CheckConstraint("basis_grams > 0", name="positive_basis"),
        sa.CheckConstraint("version > 0", name="positive_version"),
    )
    op.create_index("ix_owner_foods_owner_norm", "owner_foods", ["owner_id", "normalized_name"])
    op.create_index("ix_owner_foods_owner_active", "owner_foods", ["owner_id", "is_active"])

    op.add_column(
        "ingredient_matches",
        sa.Column(
            "owner_food_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_foods.id", ondelete="RESTRICT"),
        ),
    )
    op.create_check_constraint(
        "single_food_source",
        "ingredient_matches",
        "(food_reference_id IS NULL) OR (owner_food_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("single_food_source", "ingredient_matches")
    op.drop_column("ingredient_matches", "owner_food_id")
    op.drop_index("ix_owner_foods_owner_active", "owner_foods")
    op.drop_index("ix_owner_foods_owner_norm", "owner_foods")
    op.drop_table("owner_foods")
    op.drop_column("food_references", "serving_unit")
    op.drop_column("food_references", "serving_size_g")
