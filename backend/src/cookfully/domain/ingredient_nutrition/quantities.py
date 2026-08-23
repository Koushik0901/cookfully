from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pint import UnitRegistry

from cookfully.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal

UNIT_REGISTRY: UnitRegistry[Any] = UnitRegistry()
UNIT_REGISTRY.define("cookfully_teaspoon = 5 * milliliter")
UNIT_REGISTRY.define("cookfully_tablespoon = 15 * milliliter")
UNIT_REGISTRY.define("cookfully_cup = 240 * milliliter")

MASS_UNITS: dict[str, str] = {
    "milligram": "milligram",
    "gram": "gram",
    "kilogram": "kilogram",
    "ounce": "ounce",
    "pound": "pound",
}

VOLUME_UNITS: dict[str, str] = {
    "milliliter": "milliliter",
    "liter": "liter",
    "teaspoon": "cookfully_teaspoon",
    "tablespoon": "cookfully_tablespoon",
    "cup": "cookfully_cup",
}

_ALIAS_MAP: dict[str, str] = {
    "mg": "milligram",
    "milligram": "milligram",
    "g": "gram",
    "gram": "gram",
    "grams": "gram",
    "kg": "kilogram",
    "kilogram": "kilogram",
    "oz": "ounce",
    "ounce": "ounce",
    "ounces": "ounce",
    "lb": "pound",
    "pound": "pound",
    "pounds": "pound",
    "ml": "milliliter",
    "milliliter": "milliliter",
    "milliliters": "milliliter",
    "l": "liter",
    "liter": "liter",
    "liters": "liter",
    "tsp": "teaspoon",
    "teaspoon": "teaspoon",
    "teaspoons": "teaspoon",
    "tbsp": "tablespoon",
    "tablespoon": "tablespoon",
    "tablespoons": "tablespoon",
    "cup": "cup",
    "cups": "cup",
    "count": "item",
    "each": "item",
    "ea": "item",
    "item": "item",
    "items": "item",
}

_CANONICAL_SHORT: dict[str, str] = {
    "milligram": "mg",
    "gram": "g",
    "kilogram": "kg",
    "milliliter": "ml",
    "liter": "l",
    "teaspoon": "tsp",
    "tablespoon": "tbsp",
    "cup": "cup",
    "ounce": "oz",
    "pound": "lb",
    "item": "count",
}


@dataclass(frozen=True, slots=True)
class IngredientMeasure:
    minimum: Decimal | None
    maximum: Decimal | None
    unit_code: str | None
    optional: bool = False
    matched: bool = True

    def __post_init__(self) -> None:
        if self.minimum is not None and self.minimum < 0:
            raise DomainError("negative_quantity", "Ingredient quantity cannot be negative.", 422)
        if self.maximum is not None and self.minimum is None:
            raise DomainError("invalid_range", "Ingredient range requires a minimum.", 422)
        if self.maximum is not None and self.minimum is not None and self.maximum < self.minimum:
            raise DomainError(
                "invalid_range", "Ingredient range maximum is below its minimum.", 422
            )


@dataclass(frozen=True, slots=True)
class GramRange:
    minimum: Decimal
    maximum: Decimal
    method: str
    assumption: str | None = None


@dataclass(frozen=True, slots=True)
class Coverage:
    mass: Decimal
    required_count: Decimal
    overall: Decimal


@dataclass(frozen=True, slots=True)
class PantryQuantity:
    quantity: Decimal
    unit: str
    version: int


@dataclass(frozen=True, slots=True)
class QuantityDeduction:
    pantry_before: PantryQuantity
    grocery_before: PantryQuantity
    pantry_after: PantryQuantity
    grocery_after: PantryQuantity
    pantry_amount: Decimal
    grocery_amount: Decimal
    assumption: str


def _normalize_alias(value: str) -> str:
    normalized = value.strip().casefold().rstrip(".")
    alias = _ALIAS_MAP.get(normalized)
    if alias is None:
        raise DomainError(
            "pantry_unit_unsupported",
            "Pantry quantities require a supported mass, volume, or count unit.",
            422,
        )
    return alias


def _pint_factor(source: str, target: str) -> Decimal:
    magnitude = UNIT_REGISTRY.Quantity(1, source).to(target).magnitude
    return Decimal(str(magnitude))


def owner_serving_grams(
    measure: IngredientMeasure,
    owner_food: Any | None,
) -> GramRange | None:
    if owner_food is None:
        return None
    typical_g = getattr(owner_food, "typical_serving_g", None)
    typical_unit = getattr(owner_food, "typical_serving_unit", None)
    display_name = getattr(owner_food, "display_name", "")
    if typical_g is None or typical_unit is None:
        return None
    unit_str = str(typical_unit)
    if not unit_str.strip():
        return None
    if measure.unit_code is None:
        return None
    if measure.unit_code.strip().casefold() != unit_str.strip().casefold():
        return None
    try:
        serving_g = Decimal(str(typical_g))
    except Exception as exc:
        raise DomainError(
            "quantity_unavailable", "Ingredient quantity and unit are required.", 422
        ) from exc
    if serving_g <= 0:
        return None
    min_qty = measure.minimum if measure.minimum is not None else Decimal("1")
    max_qty = measure.maximum if measure.maximum is not None else Decimal("1")
    serving_g_str = format(serving_g.normalize(), "f")
    assumption = f"1 {unit_str} = {serving_g_str}g ({display_name})"
    return GramRange(
        quantize_decimal(min_qty * serving_g, NUTRIENT_SCALE),
        quantize_decimal(max_qty * serving_g, NUTRIENT_SCALE),
        "owner_serving",
        assumption,
    )


def to_grams(
    measure: IngredientMeasure,
    *,
    density_g_per_ml: Decimal | None = None,
    count_weight_g: Decimal | None = None,
    owner_food: Any | None = None,
) -> GramRange:
    owner_result = owner_serving_grams(measure, owner_food)
    if owner_result is not None:
        return owner_result
    if measure.minimum is None or measure.unit_code is None:
        raise DomainError("quantity_unavailable", "Ingredient quantity and unit are required.", 422)
    maximum = measure.maximum or measure.minimum
    try:
        normalized = _normalize_alias(measure.unit_code)
    except DomainError as exc:
        raise DomainError(
            "unsafe_conversion", "This unit cannot be safely converted to grams.", 422
        ) from exc
    if normalized in MASS_UNITS:
        factor = _pint_factor(MASS_UNITS[normalized], "gram")
        method = "mass"
        assumption: str | None = None
    elif normalized in VOLUME_UNITS:
        if density_g_per_ml is None or density_g_per_ml <= 0:
            raise DomainError(
                "density_required",
                "A positive density assumption is required for this conversion.",
                422,
            )
        factor = _pint_factor(VOLUME_UNITS[normalized], "milliliter") * density_g_per_ml
        method = "density"
        assumption = f"density {density_g_per_ml} g/mL"
    elif normalized == "item":
        if count_weight_g is None or count_weight_g <= 0:
            raise DomainError(
                "count_weight_required",
                "A positive count weight is required for this conversion.",
                422,
            )
        factor = count_weight_g
        method = "count_weight"
        assumption = f"count weight {count_weight_g} g"
    else:
        raise DomainError(
            "unsafe_conversion", "This unit cannot be safely converted to grams.", 422
        )
    return GramRange(
        quantize_decimal(measure.minimum * factor, NUTRIENT_SCALE),
        quantize_decimal(maximum * factor, NUTRIENT_SCALE),
        method,
        assumption,
    )


def convert_quantity(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal:
    if quantity < 0:
        raise DomainError("pantry_quantity_negative", "Pantry quantity cannot be negative.", 422)
    try:
        source_alias = _normalize_alias(from_unit)
    except DomainError as exc:
        raise DomainError(
            "pantry_unit_unsupported",
            "Pantry quantities require a supported mass, volume, or count unit.",
            422,
        ) from exc
    try:
        target_alias = _normalize_alias(to_unit)
    except DomainError as exc:
        raise DomainError(
            "pantry_unit_unsupported",
            "Pantry quantities require a supported mass, volume, or count unit.",
            422,
        ) from exc

    def dimension(alias: str) -> str:
        if alias in MASS_UNITS:
            return "mass"
        if alias in VOLUME_UNITS:
            return "volume"
        if alias == "item":
            return "count"
        raise DomainError("unsafe_conversion", "This unit cannot be safely converted.", 422)

    source_dim = dimension(source_alias)
    target_dim = dimension(target_alias)
    if source_dim != target_dim:
        raise DomainError(
            "unsafe_conversion",
            "This unit cannot be safely converted.",
            422,
        )
    if source_dim == "count":
        factor = Decimal("1")
    elif source_dim == "mass":
        factor = _pint_factor(MASS_UNITS[source_alias], MASS_UNITS[target_alias])
    else:
        factor = _pint_factor(VOLUME_UNITS[source_alias], VOLUME_UNITS[target_alias])
    return quantize_decimal(quantity * factor, NUTRIENT_SCALE)


def canonical_pantry_unit(value: str) -> str:
    normalized = _normalize_alias(value)
    canonical = _CANONICAL_SHORT.get(normalized)
    if canonical is None:
        raise DomainError(
            "pantry_unit_unsupported",
            "Pantry quantities require a supported mass, volume, or count unit.",
            422,
        )
    return canonical


def apply_quantity_deduction(
    pantry: PantryQuantity,
    grocery: PantryQuantity,
) -> QuantityDeduction:
    available_in_grocery_units = convert_quantity(pantry.quantity, pantry.unit, grocery.unit)
    grocery_amount = min(available_in_grocery_units, grocery.quantity)
    pantry_amount = convert_quantity(grocery_amount, grocery.unit, pantry.unit)
    pantry_after = PantryQuantity(
        quantize_decimal(pantry.quantity - pantry_amount, NUTRIENT_SCALE),
        canonical_pantry_unit(pantry.unit),
        pantry.version + 1,
    )
    grocery_after = PantryQuantity(
        quantize_decimal(grocery.quantity - grocery_amount, NUTRIENT_SCALE),
        canonical_pantry_unit(grocery.unit),
        grocery.version + 1,
    )
    return QuantityDeduction(
        pantry_before=PantryQuantity(
            quantize_decimal(pantry.quantity, NUTRIENT_SCALE),
            canonical_pantry_unit(pantry.unit),
            pantry.version,
        ),
        grocery_before=PantryQuantity(
            quantize_decimal(grocery.quantity, NUTRIENT_SCALE),
            canonical_pantry_unit(grocery.unit),
            grocery.version,
        ),
        pantry_after=pantry_after,
        grocery_after=grocery_after,
        pantry_amount=pantry_amount,
        grocery_amount=grocery_amount,
        assumption="Exact same-dimension conversion; no density or package-size assumption.",
    )


def reverse_quantity_deduction(
    deduction: QuantityDeduction,
    *,
    pantry: PantryQuantity,
    grocery: PantryQuantity,
) -> tuple[PantryQuantity, PantryQuantity]:
    if pantry != deduction.pantry_after or grocery != deduction.grocery_after:
        raise DomainError(
            "pantry_deduction_state_changed",
            "Pantry or grocery quantity changed after the deduction; reload before reversing.",
            409,
        )
    return (
        PantryQuantity(
            deduction.pantry_before.quantity,
            deduction.pantry_before.unit,
            pantry.version + 1,
        ),
        PantryQuantity(
            deduction.grocery_before.quantity,
            deduction.grocery_before.unit,
            grocery.version + 1,
        ),
    )


def coverage_ratio(ingredients: list[IngredientMeasure]) -> Coverage:
    required = [item for item in ingredients if not item.optional]
    measured = [item for item in required if item.minimum is not None]
    total_mass = sum((item.minimum or Decimal(0)) for item in measured)
    matched_mass = sum((item.minimum or Decimal(0)) for item in measured if item.matched)
    mass = matched_mass / total_mass if total_mass else Decimal(0)
    count = Decimal(
        sum(1 for item in required if item.matched and item.minimum is not None)
    ) / Decimal(len(required) or 1)
    mass_q = quantize_decimal(mass, NUTRIENT_SCALE)
    count_q = quantize_decimal(count, NUTRIENT_SCALE)
    return Coverage(mass_q, count_q, min(mass_q, count_q))
