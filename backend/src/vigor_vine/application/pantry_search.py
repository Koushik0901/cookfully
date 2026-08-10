from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from vigor_vine.application.pantry import convert_quantity, normalize_pantry_name
from vigor_vine.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal
from vigor_vine.infrastructure.models.pantry import PantryItem
from vigor_vine.infrastructure.models.recipes import Recipe


@dataclass(frozen=True, slots=True)
class PantrySearchItem:
    food_name: str
    quantity: Decimal
    unit: str
    match_status: str


@dataclass(slots=True)
class _AvailableItem:
    quantity: Decimal
    unit: str


@dataclass(frozen=True, slots=True)
class PantrySearchIngredient:
    food_name: str
    original_text: str
    quantity: Decimal | None
    unit: str | None
    optional: bool = False


@dataclass(frozen=True, slots=True)
class PantrySearchRecipe:
    recipe_id: str
    title: str
    ingredients: tuple[PantrySearchIngredient, ...]


@dataclass(frozen=True, slots=True)
class PantryRecipeScore:
    recipe_id: str
    title: str
    makeability: str
    coverage_ratio: Decimal
    missing_ingredients: tuple[str, ...]


def rank_makeable_recipes(
    recipes: tuple[PantrySearchRecipe, ...],
    pantry: tuple[PantrySearchItem, ...],
) -> tuple[PantryRecipeScore, ...]:
    safe_inventory: dict[str, list[PantrySearchItem]] = {}
    for item in pantry:
        if item.match_status not in {"matched", "manual"} or item.quantity <= 0:
            continue
        safe_inventory.setdefault(normalize_pantry_name(item.food_name), []).append(item)

    scores: list[PantryRecipeScore] = []
    for recipe in recipes:
        remaining = {
            key: [_AvailableItem(item.quantity, item.unit) for item in values]
            for key, values in safe_inventory.items()
        }
        required = [item for item in recipe.ingredients if not item.optional]
        missing: list[str] = []
        satisfied = 0
        for ingredient in required:
            candidates = remaining.get(normalize_pantry_name(ingredient.food_name), [])
            available = False
            if ingredient.quantity is not None and ingredient.unit:
                needed = quantize_decimal(ingredient.quantity, NUTRIENT_SCALE)
                convertible: list[tuple[_AvailableItem, Decimal]] = []
                total = Decimal(0)
                for candidate in candidates:
                    try:
                        quantity = convert_quantity(
                            candidate.quantity, candidate.unit, ingredient.unit
                        )
                    except DomainError:
                        continue
                    convertible.append((candidate, quantity))
                    total += quantity
                if total >= needed:
                    available = True
                    outstanding = needed
                    for candidate, available_amount in convertible:
                        used = min(outstanding, available_amount)
                        candidate.quantity = quantize_decimal(
                            candidate.quantity
                            - convert_quantity(used, ingredient.unit, candidate.unit),
                            NUTRIENT_SCALE,
                        )
                        outstanding -= used
                        if outstanding <= 0:
                            break
            if available:
                satisfied += 1
            else:
                missing.append(ingredient.original_text)
        coverage = quantize_decimal(
            Decimal(satisfied) / Decimal(len(required)) if required else Decimal(1),
            NUTRIENT_SCALE,
        )
        makeability = "full" if not missing else "partial" if satisfied else "none"
        scores.append(
            PantryRecipeScore(
                recipe.recipe_id,
                recipe.title,
                makeability,
                coverage,
                tuple(missing),
            )
        )
    order = {"full": 0, "partial": 1, "none": 2}
    return tuple(
        sorted(
            scores,
            key=lambda item: (
                order[item.makeability],
                -item.coverage_ratio,
                item.title.casefold(),
                item.recipe_id,
            ),
        )
    )


class PantrySearchService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def search(self, owner_id: UUID) -> tuple[PantryRecipeScore, ...]:
        with self._session_factory() as session:
            pantry = tuple(
                PantrySearchItem(
                    item.normalized_food_name,
                    item.quantity,
                    item.unit_code,
                    item.match_status,
                )
                for item in session.scalars(
                    select(PantryItem)
                    .where(PantryItem.owner_id == owner_id)
                    .order_by(PantryItem.id)
                )
            )
            recipes = tuple(
                PantrySearchRecipe(
                    str(recipe.id),
                    recipe.title,
                    tuple(
                        PantrySearchIngredient(
                            ingredient.food_name or ingredient.original_text,
                            ingredient.original_text,
                            ingredient.quantity_min,
                            ingredient.unit_code or ingredient.unit_text,
                            ingredient.optional,
                        )
                        for ingredient in recipe.ingredients
                    ),
                )
                for recipe in session.scalars(
                    select(Recipe)
                    .where(Recipe.status != "archived")
                    .options(selectinload(Recipe.ingredients))
                    .order_by(Recipe.title, Recipe.id)
                )
            )
        return rank_makeable_recipes(recipes, pantry)
