from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pint import UnitRegistry

from vigor_vine.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal

UNIT_REGISTRY: UnitRegistry[Any] = UnitRegistry()
UNIT_REGISTRY.define("vigor_teaspoon = 5 * milliliter")
UNIT_REGISTRY.define("vigor_tablespoon = 15 * milliliter")
UNIT_REGISTRY.define("vigor_cup = 240 * milliliter")
MASS_UNITS = {
    "milligram": "milligram",
    "gram": "gram",
    "kilogram": "kilogram",
    "ounce": "ounce",
    "pound": "pound",
}
VOLUME_UNITS = {
    "milliliter": "milliliter",
    "liter": "liter",
    "teaspoon": "vigor_teaspoon",
    "tablespoon": "vigor_tablespoon",
    "cup": "vigor_cup",
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


def to_grams(
    measure: IngredientMeasure,
    *,
    density_g_per_ml: Decimal | None = None,
    count_weight_g: Decimal | None = None,
) -> GramRange:
    if measure.minimum is None or measure.unit_code is None:
        raise DomainError("quantity_unavailable", "Ingredient quantity and unit are required.", 422)
    maximum = measure.maximum or measure.minimum
    if measure.unit_code in MASS_UNITS:
        factor = _pint_factor(MASS_UNITS[measure.unit_code], "gram")
        method = "mass"
        assumption = None
    elif measure.unit_code in VOLUME_UNITS:
        if density_g_per_ml is None or density_g_per_ml <= 0:
            raise DomainError(
                "density_required",
                "A positive density assumption is required for this conversion.",
                422,
            )
        factor = _pint_factor(VOLUME_UNITS[measure.unit_code], "milliliter") * density_g_per_ml
        method = "density"
        assumption = f"density {density_g_per_ml} g/mL"
    elif measure.unit_code == "item":
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


def _pint_factor(source: str, target: str) -> Decimal:
    magnitude = UNIT_REGISTRY.Quantity(1, source).to(target).magnitude
    return Decimal(str(magnitude))


def coverage_ratio(ingredients: list[IngredientMeasure]) -> Coverage:
    required = [item for item in ingredients if not item.optional]
    measured = [item for item in required if item.minimum is not None]
    total_mass = sum((item.minimum or Decimal(0)) for item in measured)
    matched_mass = sum((item.minimum or Decimal(0)) for item in measured if item.matched)
    mass = matched_mass / total_mass if total_mass else Decimal(0)
    count = Decimal(sum(1 for item in required if item.matched)) / Decimal(len(required) or 1)
    mass_q = quantize_decimal(mass, NUTRIENT_SCALE)
    count_q = quantize_decimal(count, NUTRIENT_SCALE)
    return Coverage(mass_q, count_q, min(mass_q, count_q))
