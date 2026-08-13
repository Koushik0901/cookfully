"""Add a surrogate public id to sessions and make id_hash unique."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_session_surrogate_id"
down_revision: str | None = "0011_optional_plan_goal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("UPDATE sessions SET id = gen_random_uuid() WHERE id IS NULL")
    op.alter_column("sessions", "id", nullable=False)
    existing_primary_key = sa.inspect(op.get_bind()).get_pk_constraint("sessions")["name"]
    if existing_primary_key is None:
        raise RuntimeError("sessions must have a primary key before adding its public id")
    op.drop_constraint(existing_primary_key, "sessions", type_="primary")
    op.create_primary_key("sessions_pkey", "sessions", ["id"])
    op.create_unique_constraint("uq_sessions_id_hash", "sessions", ["id_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_sessions_id_hash", "sessions", type_="unique")
    existing_primary_key = sa.inspect(op.get_bind()).get_pk_constraint("sessions")["name"]
    if existing_primary_key is None:
        raise RuntimeError("sessions must have a primary key before restoring id_hash")
    op.drop_constraint(existing_primary_key, "sessions", type_="primary")
    op.create_primary_key("sessions_pkey", "sessions", ["id_hash"])
    op.drop_column("sessions", "id")
