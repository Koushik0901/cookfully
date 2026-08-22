"""Add short-lived local-intelligence command drafts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_intelligence_drafts"
down_revision: str | None = "0023_pantry_use_by"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_intelligence_drafts_owner_expires_at",
        "intelligence_drafts",
        ["owner_id", "expires_at"],
    )
    op.create_index(
        "ix_intelligence_drafts_status_expires_at",
        "intelligence_drafts",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_intelligence_drafts_status_expires_at", table_name="intelligence_drafts")
    op.drop_index("ix_intelligence_drafts_owner_expires_at", table_name="intelligence_drafts")
    op.drop_table("intelligence_drafts")
