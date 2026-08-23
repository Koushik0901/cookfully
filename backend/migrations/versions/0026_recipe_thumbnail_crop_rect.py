"""replace thumbnail focal/zoom metadata with a crop rectangle"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_recipe_thumbnail_crop_rect"
down_revision: str | None = "0025_food_embedding_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("recipes", "thumbnail_focal_x")
    op.drop_column("recipes", "thumbnail_focal_y")
    op.drop_column("recipes", "thumbnail_zoom")
    op.add_column(
        "recipes",
        sa.Column("thumbnail_x", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "recipes",
        sa.Column("thumbnail_y", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "recipes",
        sa.Column("thumbnail_width", sa.Numeric(9, 6), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "recipes",
        sa.Column(
            "thumbnail_height", sa.Numeric(9, 6), nullable=False, server_default=sa.text("1")
        ),
    )


def downgrade() -> None:
    op.add_column(
        "recipes",
        sa.Column("thumbnail_zoom", sa.Numeric(9, 6), nullable=False, server_default=sa.text("1")),
    )
    op.add_column(
        "recipes",
        sa.Column(
            "thumbnail_focal_y", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0.5")
        ),
    )
    op.add_column(
        "recipes",
        sa.Column(
            "thumbnail_focal_x", sa.Numeric(9, 6), nullable=False, server_default=sa.text("0.5")
        ),
    )
    for name in ("thumbnail_height", "thumbnail_width", "thumbnail_y", "thumbnail_x"):
        op.drop_column("recipes", name)
