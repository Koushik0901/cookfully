"""Add missing timestamp server defaults so ORM inserts match migrated schemas."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_timestamp_server_defaults"
down_revision: str | None = "0016_onboarding_reference_choice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("recipe_collections", "grocery_shopping_stops", "remembered_grocery_placements")


def upgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=sa.func.now())
        op.alter_column(table, "updated_at", server_default=sa.func.now())


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(table, "created_at", server_default=None)
        op.alter_column(table, "updated_at", server_default=None)
