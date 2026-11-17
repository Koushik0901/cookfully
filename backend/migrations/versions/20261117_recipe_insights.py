"""Per-recipe decision-model results (hidden ingredients, facets), keyed by input fingerprint."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261117_recipe_insights"
down_revision: str | None = "20261117_decision_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipe_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_recipe_insights_kind", "recipe_insights", ["recipe_id", "kind"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_recipe_insights_kind", table_name="recipe_insights")
    op.drop_table("recipe_insights")
