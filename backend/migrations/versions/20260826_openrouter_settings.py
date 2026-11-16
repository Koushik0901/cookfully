"""Store the OpenRouter credential and decision-assist settings in the database."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_openrouter_settings"
down_revision: str | None = "0034_recipe_import_timestamp_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "openrouter_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("api_key_encrypted", sa.Text()),
        sa.Column("api_key_hint", sa.String(8)),
        sa.Column("cleanup_model", sa.String(120), nullable=False, server_default=""),
        sa.Column(
            "decision_assist_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "decision_assist_model",
            sa.String(120),
            nullable=False,
            server_default="typesafe/jev-1.14",
        ),
        sa.Column(
            "decision_assist_tolerance_dv",
            sa.Numeric(7, 6),
            nullable=False,
            server_default="0.02",
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("id = 1", name="singleton_openrouter_settings"),
        sa.CheckConstraint("version > 0", name="positive_openrouter_settings_version"),
        sa.CheckConstraint(
            "decision_assist_tolerance_dv > 0 AND decision_assist_tolerance_dv <= 0.1",
            name="valid_decision_assist_tolerance",
        ),
    )


def downgrade() -> None:
    op.drop_table("openrouter_settings")
