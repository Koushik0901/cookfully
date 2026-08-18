"""Add installation-level nutrition intelligence settings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_nutrition_intelligence"
down_revision: str | None = "0021_semantic_matching"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nutrition_intelligence_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("backend", sa.String(16), nullable=False, server_default="hashing"),
        sa.Column(
            "model_name",
            sa.String(200),
            nullable=False,
            server_default="BAAI/bge-small-en-v1.5",
        ),
        sa.Column("model_revision", sa.String(80)),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_ready_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="singleton_nutrition_intelligence_settings"),
        sa.CheckConstraint("backend IN ('hashing', 'fastembed')", name="valid_nutrition_backend"),
        sa.CheckConstraint("concurrency BETWEEN 1 AND 4", name="valid_nutrition_concurrency"),
        sa.CheckConstraint("version > 0", name="positive_nutrition_settings_version"),
    )
    op.execute(
        sa.text(
            "INSERT INTO nutrition_intelligence_settings "
            "(id, backend, model_name, concurrency, version) "
            "VALUES (1, 'hashing', 'BAAI/bge-small-en-v1.5', 1, 1)"
        )
    )


def downgrade() -> None:
    op.drop_table("nutrition_intelligence_settings")
