"""Add short-lived import preview records.

Import previews hold an unsaved, owner-scoped parse of a submitted URL so the
client can show and edit the recipe before confirming the import. Records are
short-lived and swept like other bounded-storage tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_import_previews"
down_revision: str | None = "0018_recipe_sections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_previews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_id", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_import_previews_owner_parse_id",
        "import_previews",
        ["owner_id", "parse_id"],
        unique=True,
    )
    op.create_index("ix_import_previews_expires_at", "import_previews", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_import_previews_expires_at", table_name="import_previews")
    op.drop_index("ix_import_previews_owner_parse_id", table_name="import_previews")
    op.drop_table("import_previews")