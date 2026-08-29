"""Store optional food preferences and daily fiber/sodium targets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_health_context_and_goal_nutrients"
down_revision: str | None = "0029_merge_recipe_photo_and_pantry_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "owner_accounts",
        sa.Column(
            "health_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("user_goals", sa.Column("dietary_fiber_g", sa.Numeric(20, 6), nullable=True))
    op.add_column("user_goals", sa.Column("sodium_mg", sa.Numeric(20, 6), nullable=True))
    op.drop_constraint(
        op.f("ck_user_goals_ck_user_goals_nonnegative_macros"),
        "user_goals",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_user_goals_nonnegative_goal_nutrients"),
        "user_goals",
        "protein_g >= 0 AND carbohydrate_g >= 0 AND fat_g >= 0 "
        "AND (dietary_fiber_g IS NULL OR dietary_fiber_g >= 0) "
        "AND (sodium_mg IS NULL OR sodium_mg >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_user_goals_nonnegative_goal_nutrients"),
        "user_goals",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_user_goals_ck_user_goals_nonnegative_macros"),
        "user_goals",
        "protein_g >= 0 AND carbohydrate_g >= 0 AND fat_g >= 0",
    )
    op.drop_column("user_goals", "sodium_mg")
    op.drop_column("user_goals", "dietary_fiber_g")
    op.drop_column("owner_accounts", "health_profile")
