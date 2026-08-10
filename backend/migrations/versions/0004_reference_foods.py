"""Versioned reference datasets, foods, and nutrients."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_reference_foods"
down_revision: str | None = "0003_recipes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("dataset_type", sa.String(80), nullable=False),
        sa.Column("release_id", sa.String(120), nullable=False),
        sa.Column("released_on", sa.Date(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("license", sa.String(120), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "uq_reference_datasets_release",
        "reference_datasets",
        ["provider", "dataset_type", "release_id"],
        unique=True,
    )
    op.create_index(
        "uq_reference_datasets_active_type",
        "reference_datasets",
        ["provider", "dataset_type"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "food_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reference_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("data_type", sa.String(120), nullable=False),
        sa.Column("brand_owner", sa.String(240)),
        sa.Column("food_category", sa.String(240)),
        sa.Column("basis_grams", sa.Numeric(20, 6), nullable=False),
    )
    op.create_index(
        "uq_food_references_external", "food_references", ["dataset_id", "external_id"], unique=True
    )
    op.create_index("ix_food_references_normalized_name", "food_references", ["normalized_name"])
    op.create_table(
        "food_nutrients",
        sa.Column(
            "food_reference_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("food_references.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("nutrient_code", sa.String(80), primary_key=True),
        sa.Column("amount", sa.Numeric(20, 6)),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("derivation", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("food_nutrients")
    op.drop_table("food_references")
    op.drop_table("reference_datasets")
