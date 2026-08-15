"""Reference data install requests."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_reference_data_install"
down_revision: str | None = "0014_established_onboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_data_installs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("datasets", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_reference_data_installs_owner_id", "reference_data_installs", ["owner_id"])


def downgrade() -> None:
    op.drop_table("reference_data_installs")
