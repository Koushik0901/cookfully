"""Add first-run, recipe organization, and grocery shopping-pass data."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_onboarding_recipe_library"
down_revision: str | None = "0012_session_surrogate_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_onboarding_states",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("first_action", sa.String(length=24), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("state IN ('pending', 'completed', 'dismissed')", name="valid_state"),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id"),
    )
    op.add_column(
        "recipes", sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.create_index("ix_recipes_favorite", "recipes", ["is_favorite"])
    op.create_table(
        "recipe_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0", name="nonnegative_position"),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_recipe_collections_owner_name", "recipe_collections", ["owner_id", "name"], unique=True
    )
    op.create_index(
        "uq_recipe_collections_owner_position",
        "recipe_collections",
        ["owner_id", "position"],
        unique=True,
    )
    op.create_table(
        "recipe_collection_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["recipe_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_recipe_collection_membership",
        "recipe_collection_memberships",
        ["collection_id", "recipe_id"],
        unique=True,
    )
    op.create_table(
        "recipe_meal_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint("role IN ('breakfast', 'lunch', 'dinner', 'snack')", name="valid_role"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_recipe_meal_role", "recipe_meal_roles", ["recipe_id", "role"], unique=True)
    op.create_table(
        "grocery_shopping_stops",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0", name="nonnegative_position"),
        sa.CheckConstraint("version > 0", name="positive_version"),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_grocery_shopping_stops_owner_name",
        "grocery_shopping_stops",
        ["owner_id", "name"],
        unique=True,
    )
    op.create_index(
        "uq_grocery_shopping_stops_owner_position",
        "grocery_shopping_stops",
        ["owner_id", "position"],
        unique=True,
    )
    op.create_table(
        "remembered_grocery_placements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_food_name", sa.String(length=240), nullable=False),
        sa.Column("shopping_stop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owner_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["shopping_stop_id"], ["grocery_shopping_stops.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_remembered_grocery_placement",
        "remembered_grocery_placements",
        ["owner_id", "normalized_food_name"],
        unique=True,
    )
    op.add_column("grocery_lists", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.drop_constraint("ck_grocery_lists_valid_status", "grocery_lists", type_="check")
    op.create_check_constraint(
        "valid_status",
        "grocery_lists",
        "status IN ('current', 'dirty', 'generating', 'failed', 'completed')",
    )
    op.add_column("grocery_items", sa.Column("shopping_stop_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_grocery_items_shopping_stop",
        "grocery_items",
        "grocery_shopping_stops",
        ["shopping_stop_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_grocery_items_shopping_stop", "grocery_items", type_="foreignkey")
    op.drop_column("grocery_items", "shopping_stop_id")
    op.drop_constraint("valid_status", "grocery_lists", type_="check")
    op.create_check_constraint(
        "valid_status", "grocery_lists", "status IN ('current', 'dirty', 'generating', 'failed')"
    )
    op.drop_column("grocery_lists", "completed_at")
    op.drop_index("uq_remembered_grocery_placement", table_name="remembered_grocery_placements")
    op.drop_table("remembered_grocery_placements")
    op.drop_index("uq_grocery_shopping_stops_owner_position", table_name="grocery_shopping_stops")
    op.drop_index("uq_grocery_shopping_stops_owner_name", table_name="grocery_shopping_stops")
    op.drop_table("grocery_shopping_stops")
    op.drop_index("uq_recipe_meal_role", table_name="recipe_meal_roles")
    op.drop_table("recipe_meal_roles")
    op.drop_index("uq_recipe_collection_membership", table_name="recipe_collection_memberships")
    op.drop_table("recipe_collection_memberships")
    op.drop_index("uq_recipe_collections_owner_position", table_name="recipe_collections")
    op.drop_index("uq_recipe_collections_owner_name", table_name="recipe_collections")
    op.drop_table("recipe_collections")
    op.drop_index("ix_recipes_favorite", table_name="recipes")
    op.drop_column("recipes", "is_favorite")
    op.drop_table("owner_onboarding_states")
