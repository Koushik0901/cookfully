"""Add optional use-by dates to pantry items."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_pantry_use_by"
down_revision: str | None = "0022_nutrition_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pantry_items", sa.Column("expires_on", sa.Date(), nullable=True))
    op.create_index(
        "ix_pantry_items_owner_expires_on",
        "pantry_items",
        ["owner_id", "expires_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_pantry_items_owner_expires_on", table_name="pantry_items")
    op.drop_column("pantry_items", "expires_on")
