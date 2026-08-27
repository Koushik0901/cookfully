"""Merge recipe-photo and pantry migration heads.

Revision ID: 0029_merge_recipe_photo_and_pantry_heads
Revises: 0028_staged_recipe_photo_variants, 20260825_pantry_owner_food
Create Date: 2026-08-26
"""

from collections.abc import Sequence

revision: str = "0029_merge_recipe_photo_and_pantry_heads"
down_revision: str | Sequence[str] | None = (
    "0028_staged_recipe_photo_variants",
    "20260825_pantry_owner_food",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join independent schema branches without changing the schema."""


def downgrade() -> None:
    """Split the migration graph without changing the schema."""
