"""Grocery tidy: aisle, likely-staple flag and merged names on items, plus owner overrides."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261117_grocery_tidy"
down_revision: str | None = "20261117_model_expiry_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("grocery_items", sa.Column("aisle", sa.String(24)))
    op.add_column(
        "grocery_items",
        sa.Column("likely_staple", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "grocery_items", sa.Column("merged_from", sa.JSON(), nullable=False, server_default="[]")
    )
    op.create_table(
        "grocery_tidy_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("normalized_food_name", sa.String(240), nullable=False),
        sa.Column("aisle", sa.String(24)),
        sa.Column("staple", sa.Boolean()),
        sa.Column("keep_separate", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_grocery_tidy_owner_name",
        "grocery_tidy_memories",
        ["owner_id", "normalized_food_name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_grocery_tidy_owner_name", table_name="grocery_tidy_memories")
    op.drop_table("grocery_tidy_memories")
    op.drop_column("grocery_items", "merged_from")
    op.drop_column("grocery_items", "likely_staple")
    op.drop_column("grocery_items", "aisle")
