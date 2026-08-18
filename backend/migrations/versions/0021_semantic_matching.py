"""Add semantic matching evidence, indexes, and owner memories."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_semantic_matching"
down_revision: str | None = "0020_recipe_thumbnail_crop_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ingredient_matches",
        sa.Column("resolution_kind", sa.String(24), nullable=False, server_default="confirmed"),
    )
    op.add_column("ingredient_matches", sa.Column("candidate_evidence", sa.JSON()))
    op.add_column("ingredient_matches", sa.Column("provisional_macros", sa.JSON()))

    op.create_table(
        "food_semantic_index",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "food_reference_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("food_references.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "owner_food_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_foods.id", ondelete="CASCADE"),
        ),
        sa.Column("model_name", sa.String(160), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", postgresql.BYTEA(), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("source_release_id", sa.String(120)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "((food_reference_id IS NOT NULL)::int + (owner_food_id IS NOT NULL)::int) = 1",
            name="semantic_index_single_source",
        ),
    )
    op.create_index(
        "ix_food_semantic_index_active_version",
        "food_semantic_index",
        ["model_name", "model_version"],
    )

    op.create_table(
        "food_match_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signature_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.JSON(), nullable=False),
        sa.Column(
            "food_reference_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("food_references.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "owner_food_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_foods.id", ondelete="RESTRICT"),
        ),
        sa.Column("source_release_id", sa.String(120)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "((food_reference_id IS NOT NULL)::int + (owner_food_id IS NOT NULL)::int) = 1",
            name="food_match_memory_single_source",
        ),
    )
    op.create_index(
        "uq_food_match_memories_owner_signature",
        "food_match_memories",
        ["owner_id", "signature_hash"],
        unique=True,
        postgresql_where=sa.text("active"),
    )


def downgrade() -> None:
    op.drop_index("uq_food_match_memories_owner_signature", table_name="food_match_memories")
    op.drop_table("food_match_memories")
    op.drop_index("ix_food_semantic_index_active_version", table_name="food_semantic_index")
    op.drop_table("food_semantic_index")
    op.drop_column("ingredient_matches", "provisional_macros")
    op.drop_column("ingredient_matches", "candidate_evidence")
    op.drop_column("ingredient_matches", "resolution_kind")
