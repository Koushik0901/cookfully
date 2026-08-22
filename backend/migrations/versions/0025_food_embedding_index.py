"""Add a VectorChord/pgvector-backed food embedding index."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0025_food_embedding_index"
down_revision: str | None = "0024_intelligence_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vchord CASCADE")
    op.add_column("food_semantic_index", sa.Column("embedding_vector", Vector(384)))
    op.create_index(
        "ix_food_semantic_index_vector_search",
        "food_semantic_index",
        ["embedding_vector"],
        postgresql_using="vchordrq",
        postgresql_ops={"embedding_vector": "vector_cosine_ops"},
        postgresql_where=sa.text("active AND embedding_vector IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_food_semantic_index_vector_search", table_name="food_semantic_index")
    op.drop_column("food_semantic_index", "embedding_vector")
