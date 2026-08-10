"""Durable processing jobs and transactional outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_jobs_outbox"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("progress_current", sa.Integer()),
        sa.Column("progress_total", sa.Integer()),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("terminal_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("diagnostic_reduce_at", sa.DateTime(timezone=True)),
        sa.Column("safe_metadata_delete_at", sa.DateTime(timezone=True)),
        sa.Column("celery_task_id", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("attempt >= 0 AND attempt <= max_attempts", name="valid_attempt"),
        sa.CheckConstraint("max_attempts > 0", name="positive_max_attempts"),
        sa.CheckConstraint(
            "progress_current IS NULL OR progress_current >= 0",
            name="nonnegative_progress_current",
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_total >= 0",
            name="nonnegative_progress_total",
        ),
    )
    op.create_index("ix_processing_jobs_aggregate_id", "processing_jobs", ["aggregate_id"])
    op.create_index(
        "ix_processing_jobs_status_available", "processing_jobs", ["status", "available_at"]
    )
    op.create_index(
        "ix_processing_jobs_terminal_deadline", "processing_jobs", ["terminal_deadline_at"]
    )
    op.create_index(
        "ix_processing_jobs_diagnostic_reduce_at", "processing_jobs", ["diagnostic_reduce_at"]
    )
    op.create_index(
        "ix_processing_jobs_safe_metadata_delete_at", "processing_jobs", ["safe_metadata_delete_at"]
    )
    op.create_index(
        "uq_processing_jobs_active_input",
        "processing_jobs",
        ["kind", "aggregate_id", "input_hash"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'retry_wait')"),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_unpublished", "outbox_events", ["published_at", "created_at"])


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("processing_jobs")
