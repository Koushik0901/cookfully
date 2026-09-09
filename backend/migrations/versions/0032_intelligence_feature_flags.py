"""Persist default-on Needle2 feature switches."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_intelligence_feature_flags"
down_revision: str | None = "0031_durable_cooking_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nutrition_intelligence_settings",
        sa.Column("intelligence_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "nutrition_intelligence_settings",
        sa.Column("inline_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("nutrition_intelligence_settings", "inline_enabled")
    op.drop_column("nutrition_intelligence_settings", "intelligence_enabled")
