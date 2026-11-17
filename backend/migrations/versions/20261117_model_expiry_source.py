"""Allow model-estimated expiry dates (expiry_source = 'model')."""

from collections.abc import Sequence

from alembic import op

revision: str = "20261117_model_expiry_source"
down_revision: str | None = "20261117_recipe_insights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    ("grocery_items", "valid_expiry_source", "expiry_source"),
    ("pantry_items", "valid_expiry_source", "expiry_source"),
    ("pantry_deductions", "valid_prev_expiry_source", "prev_expiry_source"),
)


def upgrade() -> None:
    for table, name, column in _TABLES:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ('auto', 'label', 'manual', 'model')")


def downgrade() -> None:
    for table, name, column in _TABLES:
        op.execute(f"UPDATE {table} SET {column} = 'auto' WHERE {column} = 'model'")  # noqa: S608
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ('auto', 'label', 'manual')")
