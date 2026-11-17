"""Cache and spend ledger for decision-model answers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261117_decision_answers"
down_revision: str | None = "20260826_openrouter_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("served_model", sa.String(160)),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(14, 9), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "uq_decision_answers_request", "decision_answers", ["model", "request_hash"], unique=True
    )
    op.create_index("ix_decision_answers_created_at", "decision_answers", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_decision_answers_created_at", table_name="decision_answers")
    op.drop_index("uq_decision_answers_request", table_name="decision_answers")
    op.drop_table("decision_answers")
