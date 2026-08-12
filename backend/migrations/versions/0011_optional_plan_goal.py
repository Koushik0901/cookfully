"""Allow food-first meal planning before a nutrition guide exists."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_optional_plan_goal"
down_revision: str | None = "0010_branded_user_foods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("meal_plans", "goal_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM meal_plans WHERE goal_id IS NULL)")):
        raise RuntimeError(
            "Cannot restore required meal-plan goals while goal-free plans exist. "
            "Create a nutrition guide for those weeks before downgrading."
        )
    op.alter_column("meal_plans", "goal_id", existing_type=sa.Uuid(), nullable=False)
