from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from cookfully.infrastructure.models.identity import OwnerAccount


class Recipe(TimestampMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        CheckConstraint("yield_quantity > 0", name="positive_yield"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "(status = 'archived' AND archived_at IS NOT NULL "
            "AND archived_from_status IS NOT NULL) "
            "OR (status <> 'archived' AND archived_at IS NULL)",
            name="archive_state_consistent",
        ),
        Index("ix_recipes_status_title", "status", "title"),
        Index("ix_recipes_favorite", "is_favorite"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    canonical_source_url: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(240))
    yield_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    yield_unit: Mapped[str] = mapped_column(String(80), nullable=False, default="servings")
    prep_minutes: Mapped[int | None] = mapped_column(Integer)
    cook_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    nutrition_state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    active_estimate_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("nutrition_estimates.id", ondelete="SET NULL", use_alter=True),
    )
    image_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    thumbnail_x: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("0.000000"), server_default=text("0")
    )
    thumbnail_y: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("0.000000"), server_default=text("0")
    )
    thumbnail_width: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("1.000000"), server_default=text("1")
    )
    thumbnail_height: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), nullable=False, default=Decimal("1.000000"), server_default=text("1")
    )
    origin_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_from_status: Mapped[str | None] = mapped_column(String(24))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    instructions: Mapped[list[RecipeInstruction]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeInstruction.position"
    )
    ingredients: Mapped[list[Ingredient]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="Ingredient.position"
    )
    sections: Mapped[list[RecipeSection]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeSection.position"
    )
    collection_memberships: Mapped[list[RecipeCollectionMembership]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    meal_roles: Mapped[list[RecipeMealRole]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeCollection(TimestampMixin, Base):
    __tablename__ = "recipe_collections"
    __table_args__ = (
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint("version > 0", name="positive_version"),
        Index("uq_recipe_collections_owner_name", "owner_id", "name", unique=True),
        Index("uq_recipe_collections_owner_position", "owner_id", "position", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owner_accounts.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    owner: Mapped[OwnerAccount] = relationship(back_populates="recipe_collections")
    memberships: Mapped[list[RecipeCollectionMembership]] = relationship(
        back_populates="collection", cascade="all, delete-orphan"
    )


class RecipeCollectionMembership(Base):
    __tablename__ = "recipe_collection_memberships"
    __table_args__ = (
        Index("uq_recipe_collection_membership", "collection_id", "recipe_id", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    collection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recipe_collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )

    collection: Mapped[RecipeCollection] = relationship(back_populates="memberships")
    recipe: Mapped[Recipe] = relationship(back_populates="collection_memberships")


class RecipeMealRole(Base):
    __tablename__ = "recipe_meal_roles"
    __table_args__ = (
        CheckConstraint("role IN ('breakfast', 'lunch', 'dinner', 'snack')", name="valid_role"),
        Index("uq_recipe_meal_role", "recipe_id", "role", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="meal_roles")


class RecipeInstruction(Base):
    __tablename__ = "recipe_instructions"
    __table_args__ = (
        CheckConstraint("position >= 0", name="nonnegative_position"),
        Index("uq_recipe_instructions_position", "recipe_id", "position", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    section_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipe_sections.id", ondelete="SET NULL")
    )
    recipe: Mapped[Recipe] = relationship(back_populates="instructions")
    section: Mapped[RecipeSection | None] = relationship(back_populates="instructions")


class RecipeSection(Base):
    __tablename__ = "recipe_sections"
    __table_args__ = (
        CheckConstraint("position >= 0", name="nonnegative_position"),
        Index("uq_recipe_sections_position", "recipe_id", "position", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    recipe: Mapped[Recipe] = relationship(back_populates="sections")
    ingredients: Mapped[list[Ingredient]] = relationship(back_populates="section")
    instructions: Mapped[list[RecipeInstruction]] = relationship(back_populates="section")


class Ingredient(TimestampMixin, Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("position >= 0", name="nonnegative_position"),
        CheckConstraint(
            "quantity_min IS NULL OR quantity_min >= 0", name="nonnegative_quantity_min"
        ),
        CheckConstraint(
            "quantity_max IS NULL OR quantity_max >= quantity_min", name="valid_quantity_range"
        ),
        CheckConstraint(
            "parse_confidence IS NULL OR (parse_confidence >= 0 AND parse_confidence <= 1)",
            name="valid_parse_confidence",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        Index("uq_ingredients_position", "recipe_id", "position", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    recipe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    section_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("recipe_sections.id", ondelete="SET NULL")
    )
    quantity_min: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    quantity_max: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    unit_code: Mapped[str | None] = mapped_column(String(80))
    unit_text: Mapped[str | None] = mapped_column(String(120))
    food_name: Mapped[str | None] = mapped_column(String(240))
    preparation: Mapped[str | None] = mapped_column(String(240))
    comment: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(String(120))
    optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parse_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unparsed")
    parse_confidence: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    parser_name: Mapped[str | None] = mapped_column(String(120))
    parser_version: Mapped[str | None] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    section: Mapped[RecipeSection | None] = relationship(back_populates="ingredients")
