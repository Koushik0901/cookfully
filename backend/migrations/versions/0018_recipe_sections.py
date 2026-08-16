"""Add recipe sections for multi-component recipes.

Sections group ingredients and instructions into components (e.g. "For the
chicken" and "For the sauce") while preserving every original line.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_recipe_sections"
down_revision: str | None = "0017_timestamp_server_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.CheckConstraint("position >= 0", name="nonnegative_position"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_recipe_sections_position", "recipe_sections", ["recipe_id", "position"], unique=True
    )
    op.add_column(
        "ingredients", sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_ingredients_section_id_recipe_sections",
        "ingredients",
        "recipe_sections",
        ["section_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "recipe_instructions",
        sa.Column("section_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_recipe_instructions_section_id_recipe_sections",
        "recipe_instructions",
        "recipe_sections",
        ["section_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_recipe_instructions_section_id_recipe_sections",
        "recipe_instructions",
        type_="foreignkey",
    )
    op.drop_column("recipe_instructions", "section_id")
    op.drop_constraint(
        "fk_ingredients_section_id_recipe_sections", "ingredients", type_="foreignkey"
    )
    op.drop_column("ingredients", "section_id")
    op.drop_index("uq_recipe_sections_position", table_name="recipe_sections")
    op.drop_table("recipe_sections")