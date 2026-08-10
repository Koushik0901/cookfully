"""Durable owner-scoped idempotency reservations and replay pointers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_idempotency"
down_revision: str | None = "0005_nutrition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owner_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('processing', 'completed')", name="valid_idempotency_state"),
        sa.CheckConstraint(
            "response_status IS NULL OR (response_status >= 100 AND response_status <= 599)",
            name="valid_idempotency_response_status",
        ),
    )
    op.create_index(
        "uq_idempotency_owner_key",
        "idempotency_records",
        ["owner_id", "idempotency_key"],
        unique=True,
    )
    op.create_index("ix_idempotency_expires_at", "idempotency_records", ["expires_at"])


def downgrade() -> None:
    op.drop_table("idempotency_records")
