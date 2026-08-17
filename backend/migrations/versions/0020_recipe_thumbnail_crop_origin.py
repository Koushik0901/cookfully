"""Add recipe thumbnail focal point and provenance metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_recipe_thumbnail_crop_origin"
down_revision: str | None = "0019_import_previews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recipes",
        sa.Column(
            "thumbnail_focal_x",
            sa.Numeric(9, 6),
            nullable=False,
            server_default="0.500000",
        ),
    )
    op.add_column(
        "recipes",
        sa.Column(
            "thumbnail_focal_y",
            sa.Numeric(9, 6),
            nullable=False,
            server_default="0.500000",
        ),
    )
    op.add_column(
        "recipes",
        sa.Column(
            "thumbnail_zoom",
            sa.Numeric(9, 6),
            nullable=False,
            server_default="1.000000",
        ),
    )
    op.add_column(
        "recipes",
        sa.Column("origin_kind", sa.String(length=24), nullable=False, server_default="manual"),
    )


def downgrade() -> None:
    op.drop_column("recipes", "origin_kind")
    op.drop_column("recipes", "thumbnail_zoom")
    op.drop_column("recipes", "thumbnail_focal_y")
    op.drop_column("recipes", "thumbnail_focal_x")
