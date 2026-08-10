from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from vigor_vine.domain.common import (
    NUTRIENT_SCALE,
    SERVING_SCALE,
    DomainError,
    display_calories,
    display_macro,
    quantize_decimal,
)

NutrientField = Literal["calories_kcal", "protein_g", "carbohydrate_g", "fat_g"]


@dataclass(frozen=True, slots=True)
class MacroValues:
    calories_kcal: Decimal | None
    protein_g: Decimal | None
    carbohydrate_g: Decimal | None
    fat_g: Decimal | None


@dataclass(frozen=True, slots=True)
class IngredientNutrition:
    macros: MacroValues
    matched: bool


@dataclass(frozen=True, slots=True)
class NutritionEstimateValue:
    macros: MacroValues
    basis_servings: Decimal
    coverage: Decimal


@dataclass(frozen=True, slots=True)
class NutritionCorrectionValue:
    value: Decimal
    active: bool


@dataclass(frozen=True, slots=True)
class ResolvedMacros:
    values: MacroValues
    sources: dict[NutrientField, str]
    display: dict[str, str | None]


def rollup_per_serving(
    contributions: list[IngredientNutrition],
    servings: Decimal,
    *,
    coverage: Decimal,
) -> NutritionEstimateValue:
    serving_value = quantize_decimal(servings, SERVING_SCALE)
    if serving_value <= 0:
        raise DomainError("invalid_servings", "Serving quantity must be greater than zero.", 422)
    if not Decimal(0) <= coverage <= Decimal(1):
        raise DomainError("invalid_coverage", "Coverage must be between zero and one.", 422)

    def nutrient(field: NutrientField) -> Decimal | None:
        matched = [item for item in contributions if item.matched]
        values = [getattr(item.macros, field) for item in matched]
        if not values or any(value is None for value in values):
            return None
        total = sum((value for value in values if value is not None), Decimal(0))
        return quantize_decimal(total / serving_value, NUTRIENT_SCALE)

    return NutritionEstimateValue(
        MacroValues(
            nutrient("calories_kcal"),
            nutrient("protein_g"),
            nutrient("carbohydrate_g"),
            nutrient("fat_g"),
        ),
        serving_value,
        quantize_decimal(coverage, NUTRIENT_SCALE),
    )


def resolved_macros(
    automatic: MacroValues,
    corrections: dict[NutrientField, NutritionCorrectionValue],
) -> ResolvedMacros:
    fields: tuple[NutrientField, ...] = (
        "calories_kcal",
        "protein_g",
        "carbohydrate_g",
        "fat_g",
    )
    values: dict[NutrientField, Decimal | None] = {}
    sources: dict[NutrientField, str] = {}
    for field in fields:
        correction = corrections.get(field)
        if correction is not None and correction.active:
            values[field] = quantize_decimal(correction.value, NUTRIENT_SCALE)
            sources[field] = "manual"
        else:
            values[field] = getattr(automatic, field)
            sources[field] = "automatic"
    resolved = MacroValues(**values)
    return ResolvedMacros(
        resolved,
        sources,
        {
            "caloriesKcal": (
                display_calories(resolved.calories_kcal)
                if resolved.calories_kcal is not None
                else None
            ),
            "proteinG": display_macro(resolved.protein_g)
            if resolved.protein_g is not None
            else None,
            "carbohydrateG": (
                display_macro(resolved.carbohydrate_g)
                if resolved.carbohydrate_g is not None
                else None
            ),
            "fatG": display_macro(resolved.fat_g) if resolved.fat_g is not None else None,
        },
    )
