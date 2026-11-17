"""Decision-model labels for USDA foods (state, kind, origin, flavour, allergens)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261117_food_labels"
down_revision: str | None = "20261117_grocery_tidy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "food_labels",
        sa.Column(
            "food_reference_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("food_references.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("food_labels")
