"""Persist recipe-import cleanup and remote fallback switches."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_recipe_import_cleanup"
down_revision: str | None = "0032_intelligence_feature_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_import_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cleanup_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "openrouter_fallback_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="singleton_recipe_import_settings"),
        sa.CheckConstraint("version > 0", name="positive_recipe_import_settings_version"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("recipe_import_settings")
