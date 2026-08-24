"""add expiry to grocery and pantry"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260824_add_expiry_to_grocery_and_pantry"
down_revision: str | None = "0027_default_neural_matching"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "grocery_items",
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("grocery_items", sa.Column("expires_on", sa.Date(), nullable=True))
    op.add_column("grocery_items", sa.Column("expiry_source", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "valid_expiry_source",
        "grocery_items",
        "expiry_source IN ('auto', 'label', 'manual')",
    )
    op.create_check_constraint(
        "expires_on_requires_purchased_at",
        "grocery_items",
        "expires_on IS NULL OR purchased_at IS NOT NULL",
    )
    op.add_column(
        "pantry_items",
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("pantry_items", sa.Column("expiry_source", sa.String(length=10), nullable=True))
    op.create_check_constraint(
        "valid_expiry_source",
        "pantry_items",
        "expiry_source IN ('auto', 'label', 'manual')",
    )


def downgrade() -> None:
    op.drop_constraint("valid_expiry_source", "pantry_items", type_="check")
    op.drop_column("pantry_items", "expiry_source")
    op.drop_column("pantry_items", "purchased_at")
    op.drop_constraint("expires_on_requires_purchased_at", "grocery_items", type_="check")
    op.drop_constraint("valid_expiry_source", "grocery_items", type_="check")
    op.drop_column("grocery_items", "expiry_source")
    op.drop_column("grocery_items", "expires_on")
    op.drop_column("grocery_items", "purchased_at")
