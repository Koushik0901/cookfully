"""Avoid-list warnings for recipes and planned meals, computed when they are read.

Computing at read time means a warning always reflects the current recipe and the current avoid list
without any stored state to go stale.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from cookfully.domain.avoid_list import AvoidLine, AvoidWarning, find_avoided
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.recipes import Ingredient, Recipe

MAX_AVOID_ITEMS = 24


def owner_avoid_list(session: Session) -> tuple[str, ...]:
    """The single owner's avoid list, cleaned; empty when none is set."""

    profile = session.scalar(
        select(OwnerAccount.health_profile).order_by(OwnerAccount.created_at).limit(1)
    )
    if not isinstance(profile, dict):
        return ()
    # The API stores the profile by alias; accept the field name too for older rows.
    raw = profile.get("avoidIngredients", profile.get("avoid_ingredients"))
    if not isinstance(raw, list):
        return ()
    items = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    return tuple(dict.fromkeys(items))[:MAX_AVOID_ITEMS]


def ingredient_warnings(
    ingredients: Iterable[Ingredient], avoid: Sequence[str]
) -> tuple[AvoidWarning, ...]:
    if not avoid:
        return ()
    lines = [
        AvoidLine(item.id, f"{item.original_text} {item.food_name or ''}") for item in ingredients
    ]
    return find_avoided(lines, avoid)


def recipe_avoid_warnings(session: Session, recipe: Recipe) -> tuple[AvoidWarning, ...]:
    return ingredient_warnings(recipe.ingredients, owner_avoid_list(session))


def plan_avoid_warnings(
    session: Session, recipe_ids: Iterable[UUID | None]
) -> dict[UUID, tuple[str, ...]]:
    """Avoided items per planned recipe, for recipes that have any."""

    avoid = owner_avoid_list(session)
    wanted = {recipe_id for recipe_id in recipe_ids if recipe_id is not None}
    if not avoid or not wanted:
        return {}
    recipes = session.scalars(
        select(Recipe).where(Recipe.id.in_(wanted)).options(selectinload(Recipe.ingredients))
    ).all()
    result: dict[UUID, tuple[str, ...]] = {}
    for recipe in recipes:
        items = tuple(dict.fromkeys(w.item for w in ingredient_warnings(recipe.ingredients, avoid)))
        if items:
            result[recipe.id] = items
    return result
