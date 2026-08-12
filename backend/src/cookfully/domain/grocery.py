from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from cookfully.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal


@dataclass(frozen=True, slots=True)
class GroceryIngredient:
    meal_plan_entry_id: UUID
    ingredient_id: UUID | None
    original_text: str
    food_name: str
    quantity: Decimal | None
    unit_code: str | None
    unit_text: str | None
    planned_servings: Decimal
    recipe_yield: Decimal


@dataclass(frozen=True, slots=True)
class GrocerySource:
    meal_plan_entry_id: UUID
    ingredient_id: UUID | None
    original_text: str
    quantity_contribution: Decimal | None


@dataclass(frozen=True, slots=True)
class ProposedGroceryItem:
    normalized_food_name: str
    display_name: str
    quantity: Decimal | None
    unit_code: str | None
    unit_text: str | None
    aggregation_key: str | None
    needs_review: bool
    position: int
    sources: tuple[GrocerySource, ...]


@dataclass(frozen=True, slots=True)
class _Unit:
    dimension: str
    canonical: str
    factor: Decimal


UNITS = {
    "g": _Unit("mass", "g", Decimal("1")),
    "gram": _Unit("mass", "g", Decimal("1")),
    "grams": _Unit("mass", "g", Decimal("1")),
    "kg": _Unit("mass", "g", Decimal("1000")),
    "mg": _Unit("mass", "g", Decimal("0.001")),
    "oz": _Unit("mass", "g", Decimal("28.349523125")),
    "lb": _Unit("mass", "g", Decimal("453.59237")),
    "ml": _Unit("volume", "ml", Decimal("1")),
    "l": _Unit("volume", "ml", Decimal("1000")),
    "tsp": _Unit("volume", "ml", Decimal("4.92892159375")),
    "tbsp": _Unit("volume", "ml", Decimal("14.78676478125")),
    "cup": _Unit("volume", "ml", Decimal("236.5882365")),
}


def normalize_food_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    words = re.sub(r"[^a-z0-9]+", " ", folded).strip().split()
    normalized: list[str] = []
    for word in words:
        if len(word) > 4 and word.endswith("ies"):
            word = f"{word[:-3]}y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        normalized.append(word)
    return " ".join(normalized)


def _unit(code: str | None, text: str | None) -> _Unit | None:
    value = (code or text or "").strip().lower().rstrip(".")
    if not value:
        return None
    known = UNITS.get(value)
    if known is not None:
        return known
    return _Unit(f"unit:{value}", value, Decimal(1))


def _scaled(value: GroceryIngredient, unit: _Unit | None) -> Decimal | None:
    if value.quantity is None:
        return None
    if value.recipe_yield <= 0 or value.planned_servings <= 0:
        raise DomainError(
            "invalid_grocery_scale",
            "Recipe yield and planned servings must be greater than zero.",
            422,
        )
    factor = unit.factor if unit is not None else Decimal(1)
    return quantize_decimal(
        value.quantity * value.planned_servings / value.recipe_yield * factor,
        NUTRIENT_SCALE,
    )


def aggregate_grocery_ingredients(
    ingredients: list[GroceryIngredient],
) -> list[ProposedGroceryItem]:
    prepared: list[tuple[int, GroceryIngredient, str, _Unit | None, Decimal | None]] = []
    dimensions: defaultdict[str, set[str]] = defaultdict(set)
    for position, value in enumerate(ingredients):
        normalized = normalize_food_name(value.food_name)
        if not normalized:
            normalized = normalize_food_name(value.original_text) or "unidentified ingredient"
        unit = _unit(value.unit_code, value.unit_text)
        quantity = _scaled(value, unit)
        dimension = unit.dimension if unit is not None else "unitless"
        dimensions[normalized].add("unquantified" if quantity is None else dimension)
        prepared.append((position, value, normalized, unit, quantity))

    grouped: dict[str, list[tuple[int, GroceryIngredient, str, _Unit | None, Decimal | None]]] = {}
    for row in prepared:
        position, value, normalized, unit, quantity = row
        dimension = unit.dimension if unit is not None else "unitless"
        key = (
            f"{normalized}|{dimension}:{unit.canonical if unit else 'each'}"
            if quantity is not None
            else f"unquantified:{position}"
        )
        grouped.setdefault(key, []).append(row)

    result: list[ProposedGroceryItem] = []
    for rows in grouped.values():
        first_position, first, normalized, unit, quantity = rows[0]
        sources = tuple(
            GrocerySource(
                meal_plan_entry_id=value.meal_plan_entry_id,
                ingredient_id=value.ingredient_id,
                original_text=value.original_text,
                quantity_contribution=scaled,
            )
            for _, value, _, _, scaled in rows
        )
        total = (
            quantize_decimal(
                sum((scaled for *_, scaled in rows if scaled is not None), Decimal(0)),
                NUTRIENT_SCALE,
            )
            if quantity is not None
            else None
        )
        incompatible = len(dimensions[normalized]) > 1
        result.append(
            ProposedGroceryItem(
                normalized_food_name=normalized,
                display_name=first.food_name.strip() or first.original_text.strip(),
                quantity=total,
                unit_code=unit.canonical if unit is not None else None,
                unit_text=unit.canonical if unit is not None else None,
                aggregation_key=(
                    f"{normalized}|{unit.dimension}:{unit.canonical}"
                    if total is not None and unit is not None
                    else f"{normalized}|unitless:each"
                    if total is not None
                    else None
                ),
                needs_review=incompatible or total is None,
                position=first_position,
                sources=sources,
            )
        )
    return result
