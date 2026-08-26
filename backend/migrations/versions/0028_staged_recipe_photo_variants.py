"""Add expiring staged recipe media and one responsive card derivative."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_staged_recipe_photo_variants"
down_revision: str | None = "0027_default_neural_matching"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_photo_stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("detail_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("card_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["detail_asset_id"], ["media_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["card_asset_id"], ["media_assets.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_recipe_photo_stages_owner_id", "recipe_photo_stages", ["owner_id"])
    op.create_index("ix_recipe_photo_stages_expires_at", "recipe_photo_stages", ["expires_at"])
    op.create_table(
        "recipe_photo_derivatives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint("role IN ('card')", name="recipe_photo_derivative_role"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_recipe_photo_derivatives_recipe_id", "recipe_photo_derivatives", ["recipe_id"]
    )
    op.create_index(
        "uq_recipe_photo_derivative_role",
        "recipe_photo_derivatives",
        ["recipe_id", "role"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_recipe_photo_derivative_role", table_name="recipe_photo_derivatives")
    op.drop_index("ix_recipe_photo_derivatives_recipe_id", table_name="recipe_photo_derivatives")
    op.drop_table("recipe_photo_derivatives")
    op.drop_index("ix_recipe_photo_stages_expires_at", table_name="recipe_photo_stages")
    op.drop_index("ix_recipe_photo_stages_owner_id", table_name="recipe_photo_stages")
    op.drop_table("recipe_photo_stages")
