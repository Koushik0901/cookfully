"""Recipe aggregate, ordered instructions, and exact ingredients."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_recipes"
down_revision: str | None = "0002_jobs_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("canonical_source_url", sa.Text()),
        sa.Column("source_name", sa.String(240)),
        sa.Column("yield_quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("yield_unit", sa.String(80), nullable=False),
        sa.Column("prep_minutes", sa.Integer()),
        sa.Column("cook_minutes", sa.Integer()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("nutrition_state", sa.String(24), nullable=False),
        sa.Column("active_estimate_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "image_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="SET NULL"),
        ),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("archived_from_status", sa.String(24)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("yield_quantity > 0", name="positive_yield"),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.CheckConstraint(
            "(status = 'archived' AND archived_at IS NOT NULL "
            "AND archived_from_status IS NOT NULL) "
            "OR (status <> 'archived' AND archived_at IS NULL)",
            name="archive_state_consistent",
        ),
    )
    op.create_index("ix_recipes_status_title", "recipes", ["status", "title"])
    op.create_table(
        "recipe_instructions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="nonnegative_position"),
    )
    op.create_index(
        "uq_recipe_instructions_position",
        "recipe_instructions",
        ["recipe_id", "position"],
        unique=True,
    )
    op.create_table(
        "ingredients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("quantity_min", sa.Numeric(20, 6)),
        sa.Column("quantity_max", sa.Numeric(20, 6)),
        sa.Column("unit_code", sa.String(80)),
        sa.Column("unit_text", sa.String(120)),
        sa.Column("food_name", sa.String(240)),
        sa.Column("preparation", sa.String(240)),
        sa.Column("comment", sa.Text()),
        sa.Column("purpose", sa.String(120)),
        sa.Column("optional", sa.Boolean(), nullable=False),
        sa.Column("parse_status", sa.String(24), nullable=False),
        sa.Column("parse_confidence", sa.Numeric(7, 6)),
        sa.Column("parser_name", sa.String(120)),
        sa.Column("parser_version", sa.String(80)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name="nonnegative_position"),
        sa.CheckConstraint(
            "quantity_min IS NULL OR quantity_min >= 0",
            name="nonnegative_quantity_min",
        ),
        sa.CheckConstraint(
            "quantity_max IS NULL OR quantity_max >= quantity_min",
            name="valid_quantity_range",
        ),
        sa.CheckConstraint(
            "parse_confidence IS NULL OR (parse_confidence >= 0 AND parse_confidence <= 1)",
            name="valid_parse_confidence",
        ),
        sa.CheckConstraint("version > 0", name="positive_version"),
    )
    op.create_index("ix_ingredients_recipe_id", "ingredients", ["recipe_id"])
    op.create_index(
        "uq_ingredients_position", "ingredients", ["recipe_id", "position"], unique=True
    )
    op.create_foreign_key(
        "fk_media_assets_recipe_id_recipes",
        "media_assets",
        "recipes",
        ["recipe_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_media_assets_recipe_id_recipes", "media_assets", type_="foreignkey")
    op.drop_table("ingredients")
    op.drop_table("recipe_instructions")
    op.drop_table("recipes")
