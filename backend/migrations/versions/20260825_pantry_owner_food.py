"""allow pantry items to use owner-created foods"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_pantry_owner_food"
down_revision: str | None = "20260825_store_prev_expiry_on_deduction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pantry_items",
        sa.Column("owner_food_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pantry_items_owner_food_id",
        "pantry_items",
        "owner_foods",
        ["owner_food_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "single_pantry_food_source",
        "pantry_items",
        "(food_reference_id IS NULL) OR (owner_food_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("single_pantry_food_source", "pantry_items", type_="check")
    op.drop_constraint("fk_pantry_items_owner_food_id", "pantry_items", type_="foreignkey")
    op.drop_column("pantry_items", "owner_food_id")
