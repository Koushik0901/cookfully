"""Per-feature decision-model settings and a monthly spend cap.

The matching assist's enable switch and model move into ``decision_features``. Only values that
differ from the defaults are written, so an untouched install picks up the default model panel.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261117_decision_features"
down_revision: str | None = "20261117_decision_answers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_MODEL = "typesafe/jev-1.14"


def upgrade() -> None:
    op.add_column(
        "openrouter_settings",
        sa.Column("decision_features", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "openrouter_settings",
        sa.Column(
            "decision_monthly_cap_usd", sa.Numeric(8, 2), nullable=False, server_default="2.00"
        ),
    )
    op.create_check_constraint(
        "valid_decision_monthly_cap",
        "openrouter_settings",
        "decision_monthly_cap_usd >= 0 AND decision_monthly_cap_usd <= 100",
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, decision_assist_enabled, decision_assist_model FROM openrouter_settings"
        )
    ).all()
    for row_id, enabled, model in rows:
        if enabled and model == DEFAULT_MODEL:
            continue
        features = {"match_referee": {"enabled": bool(enabled), "models": [model] if model else []}}
        connection.execute(
            sa.text("UPDATE openrouter_settings SET decision_features = :features WHERE id = :id"),
            {"features": json.dumps(features), "id": row_id},
        )
    op.drop_column("openrouter_settings", "decision_assist_model")
    op.drop_column("openrouter_settings", "decision_assist_enabled")


def downgrade() -> None:
    op.add_column(
        "openrouter_settings",
        sa.Column(
            "decision_assist_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.add_column(
        "openrouter_settings",
        sa.Column(
            "decision_assist_model", sa.String(120), nullable=False, server_default=DEFAULT_MODEL
        ),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, decision_features FROM openrouter_settings")
    ).all()
    for row_id, features in rows:
        data = features if isinstance(features, dict) else json.loads(features or "{}")
        entry = data.get("match_referee") or {}
        models = entry.get("models") or [DEFAULT_MODEL]
        connection.execute(
            sa.text(
                "UPDATE openrouter_settings SET decision_assist_enabled = :enabled, "
                "decision_assist_model = :model WHERE id = :id"
            ),
            {"enabled": bool(entry.get("enabled", True)), "model": models[0], "id": row_id},
        )
    op.drop_constraint("valid_decision_monthly_cap", "openrouter_settings", type_="check")
    op.drop_column("openrouter_settings", "decision_monthly_cap_usd")
    op.drop_column("openrouter_settings", "decision_features")
