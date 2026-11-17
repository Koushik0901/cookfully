"""Raise the default auto-resolve tolerance from 2% to 8% of daily value.

Measured on the 140-line gold set with the Jev and Clef panel
(docs/decision-model-experiments/app-eval.md): 8% resolves 44 uncertain lines with none wrong,
against 38 at 2%, and leaves fewer lines for a person. Existing rows still on the old default
move to the new one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261117_tolerance_default"
down_revision: str | None = "20261117_food_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("openrouter_settings", "decision_assist_tolerance_dv", server_default="0.08")
    op.execute(
        sa.text(
            "UPDATE openrouter_settings SET decision_assist_tolerance_dv = 0.08 "
            "WHERE decision_assist_tolerance_dv = 0.02"
        )
    )


def downgrade() -> None:
    op.alter_column("openrouter_settings", "decision_assist_tolerance_dv", server_default="0.02")
    op.execute(
        sa.text(
            "UPDATE openrouter_settings SET decision_assist_tolerance_dv = 0.02 "
            "WHERE decision_assist_tolerance_dv = 0.08"
        )
    )
