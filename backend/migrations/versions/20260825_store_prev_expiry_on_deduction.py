"""store prev expiry on pantry deduction for reversible expiry"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_store_prev_expiry_on_deduction"
down_revision: str | None = "20260824_add_expiry_to_grocery_and_pantry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pantry_deductions",
        sa.Column("prev_purchased_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pantry_deductions",
        sa.Column("prev_expires_on", sa.Date(), nullable=True),
    )
    op.add_column(
        "pantry_deductions",
        sa.Column("prev_expiry_source", sa.String(length=10), nullable=True),
    )
    op.create_check_constraint(
        "valid_prev_expiry_source",
        "pantry_deductions",
        "prev_expiry_source IN ('auto', 'label', 'manual')",
    )


def downgrade() -> None:
    op.drop_constraint("valid_prev_expiry_source", "pantry_deductions", type_="check")
    op.drop_column("pantry_deductions", "prev_expiry_source")
    op.drop_column("pantry_deductions", "prev_expires_on")
    op.drop_column("pantry_deductions", "prev_purchased_at")
