"""default ingredient matching to the neural embedding model"""

import sqlalchemy as sa
from alembic import op

revision: str = "0027_default_neural_matching"
down_revision: str | None = "0026_recipe_thumbnail_crop_rect"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "nutrition_intelligence_settings",
        "backend",
        existing_type=sa.String(16),
        server_default=sa.text("'fastembed'"),
    )
    op.alter_column(
        "nutrition_intelligence_settings",
        "model_name",
        existing_type=sa.String(200),
        server_default=sa.text("'BAAI/bge-small-en-v1.5'"),
    )
    op.execute(
        "UPDATE nutrition_intelligence_settings "
        "SET backend = 'fastembed', model_name = 'BAAI/bge-small-en-v1.5' "
        "WHERE backend = 'hashing'"
    )


def downgrade() -> None:
    op.alter_column(
        "nutrition_intelligence_settings",
        "backend",
        existing_type=sa.String(16),
        server_default=sa.text("'hashing'"),
    )
