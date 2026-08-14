"""Dismiss onboarding for owners that predate explicit first-run state."""

from collections.abc import Sequence

from alembic import op

revision: str = "0014_established_onboarding"
down_revision: str | None = "0013_onboarding_recipe_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO owner_onboarding_states
            (owner_id, state, first_action, resolved_at, version)
        SELECT id, 'dismissed', NULL, CURRENT_TIMESTAMP, 1
        FROM owner_accounts AS owner
        WHERE NOT EXISTS (
            SELECT 1
            FROM owner_onboarding_states AS onboarding
            WHERE onboarding.owner_id = owner.id
        )
        """
    )


def downgrade() -> None:
    # A normal user resolution increments version to 2. Version-1 dismissed
    # rows therefore identify only the legacy backfill performed above.
    op.execute(
        """
        DELETE FROM owner_onboarding_states
        WHERE state = 'dismissed'
          AND first_action IS NULL
          AND version = 1
        """
    )
