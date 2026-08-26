from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from cookfully.application.food_match_memories import remember_food_choice
from cookfully.application.ingredient_engine import engine
from cookfully.domain.common import DomainError, uuid7
from cookfully.domain.food_semantics import concept_signature, profile_from_text
from cookfully.domain.ingredient_nutrition.quantities import IngredientMeasure
from cookfully.domain.volume_assumptions import density_for
from cookfully.infrastructure.models.nutrition import IngredientMatch
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.recipes import Ingredient, Recipe
from cookfully.infrastructure.models.reference_foods import FoodReference
from cookfully.infrastructure.repositories.nutrition import NutritionRepository


@dataclass(frozen=True, slots=True)
class FoodMatchPropagation:
    recipes_updated: int
    ingredients_updated: int


def propagate_food_choice(
    session: Session,
    *,
    owner_id: UUID,
    ingredient_name: str,
    food_reference_id: UUID | None = None,
    owner_food_id: UUID | None = None,
    jobs: Any | None = None,
) -> FoodMatchPropagation:
    """Persist an owner choice and apply it to matching unresolved ingredients.

    Existing recipe-level manual corrections remain authoritative. Other active
    matches for the same semantic ingredient are replaced with a manual match and
    queued for a nutrition rollup so every screen converges on the same choice.
    """

    signature = concept_signature(profile_from_text(ingredient_name))
    food_reference = session.get(FoodReference, food_reference_id) if food_reference_id else None
    owner_food = session.get(OwnerFood, owner_food_id) if owner_food_id else None
    if food_reference is None and owner_food is None:
        raise DomainError("food_reference_not_found", "Food match was not found.", 404)
    remember_food_choice(
        session,
        owner_id=owner_id,
        food_name=ingredient_name,
        food_reference_id=food_reference.id if food_reference else None,
        owner_food_id=owner_food.id if owner_food else None,
        source_release_id=food_reference.dataset.release_id if food_reference else None,
    )

    recipes_updated = 0
    ingredients_updated = 0
    candidate_rows = session.execute(
        select(Ingredient, Recipe)
        .join(Recipe, Ingredient.recipe_id == Recipe.id)
        .where(Recipe.status != "archived")
    ).all()
    candidate_ingredients = [
        (ingredient, recipe)
        for ingredient, recipe in candidate_rows
        if _ingredient_signature(ingredient) == signature
    ]
    active_matches = (
        {
            match.ingredient_id: match
            for match in session.scalars(
                select(IngredientMatch).where(
                    IngredientMatch.ingredient_id.in_(
                        ingredient.id for ingredient, _recipe in candidate_ingredients
                    ),
                    IngredientMatch.active.is_(True),
                )
            )
        }
        if candidate_ingredients
        else {}
    )
    repository = NutritionRepository(session)
    changed_recipes: dict[UUID, Recipe] = {}
    for ingredient, recipe in candidate_ingredients:
        active = active_matches.get(ingredient.id)
        if active is not None and active.status == "manual":
            continue
        grams_min, grams_max, method, assumption = _grams(
            ingredient, food_reference=food_reference, owner_food=owner_food
        )
        repository.activate_match(
            IngredientMatch(
                ingredient_id=ingredient.id,
                food_reference_id=food_reference.id if food_reference else None,
                owner_food_id=owner_food.id if owner_food else None,
                status="manual",
                match_method="pantry_memory",
                match_score=None,
                grams_min=grams_min,
                grams_max=grams_max,
                conversion_method=method,
                density_g_per_ml=(
                    density_for(food_reference.description) if food_reference else None
                ),
                assumption_text=assumption,
                source_release_id=(food_reference.dataset.release_id if food_reference else None),
                input_hash=recipe.input_hash,
                active=True,
            )
        )
        ingredients_updated += 1
        changed_recipes[recipe.id] = recipe
    for recipe in changed_recipes.values():
        recipe.status = "processing"
        recipe.nutrition_state = "stale"
        recipe.version += 1
        recipes_updated += 1
        if jobs is not None:
            jobs.accept_in_session(
                session,
                kind="nutrition_match",
                aggregate_type="recipe",
                aggregate_id=recipe.id,
                input_hash=recipe.input_hash,
                trace_id=f"food-match-{uuid7()}",
            )
    return FoodMatchPropagation(recipes_updated, ingredients_updated)


def _ingredient_signature(ingredient: Ingredient) -> str:
    return concept_signature(profile_from_text(ingredient.food_name or ingredient.original_text))


def _grams(
    ingredient: Ingredient,
    *,
    food_reference: FoodReference | None,
    owner_food: OwnerFood | None,
) -> tuple[Decimal | None, Decimal | None, str | None, str | None]:
    try:
        converted = engine.to_grams(
            IngredientMeasure(
                ingredient.quantity_min,
                ingredient.quantity_max,
                ingredient.unit_code,
                ingredient.optional,
            ),
            owner_food=owner_food,
            density_g_per_ml=(density_for(food_reference.description) if food_reference else None),
        )
        return converted.minimum, converted.maximum, converted.method, converted.assumption
    except DomainError:
        return None, None, None, None
