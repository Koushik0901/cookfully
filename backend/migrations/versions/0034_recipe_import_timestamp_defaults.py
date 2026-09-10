"""Add timestamp defaults to recipe-import settings created by 0033."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_recipe_import_timestamp_defaults"
down_revision: str | None = "0033_recipe_import_cleanup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("recipe_import_settings", "created_at", server_default=sa.func.now())
    op.alter_column("recipe_import_settings", "updated_at", server_default=sa.func.now())


def downgrade() -> None:
    op.alter_column("recipe_import_settings", "created_at", server_default=None)
    op.alter_column("recipe_import_settings", "updated_at", server_default=None)
