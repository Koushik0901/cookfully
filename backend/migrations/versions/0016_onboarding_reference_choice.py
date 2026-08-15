"""Onboarding reference-data choice."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_onboarding_reference_choice"
down_revision: str | None = "0015_reference_data_install"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("owner_onboarding_states", sa.Column("reference_data_choice", sa.String(32)))


def downgrade() -> None:
    op.drop_column("owner_onboarding_states", "reference_data_choice")
