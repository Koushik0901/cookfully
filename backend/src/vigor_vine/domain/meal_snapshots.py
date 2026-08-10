from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from vigor_vine.domain.common import (
    DISPLAY_CALORIE_SCALE,
    DISPLAY_MACRO_SCALE,
    NUTRIENT_SCALE,
    SERVING_SCALE,
    DomainError,
    quantize_decimal,
)
from vigor_vine.domain.nutrition import MacroValues

NutritionReliability = Literal["source_provided", "estimated", "partial", "manual"]


@dataclass(frozen=True, slots=True)
class SnapshotSource:
    recipe_id: UUID | None
    estimate_id: UUID | None
    recipe_title: str
    macros: MacroValues
    status: NutritionReliability
    coverage_ratio: Decimal


@dataclass(frozen=True, slots=True)
class MealNutritionSnapshotValue:
    recipe_id: UUID | None
    estimate_id: UUID | None
    recipe_title: str
    basis_servings: Decimal
    calories_kcal: Decimal | None
    protein_g: Decimal | None
    carbohydrate_g: Decimal | None
    fat_g: Decimal | None
    status: NutritionReliability
    coverage_ratio: Decimal


def _servings(value: Decimal) -> Decimal:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -3:
        raise DomainError(
            "servings_precision", "Servings may contain at most three decimal places.", 422
        )
    result = quantize_decimal(value, SERVING_SCALE)
    if result <= 0:
        raise DomainError("invalid_servings", "Serving quantity must be greater than zero.", 422)
    return result


def create_snapshot(source: SnapshotSource, servings: Decimal) -> MealNutritionSnapshotValue:
    basis = _servings(servings)
    coverage = quantize_decimal(source.coverage_ratio, NUTRIENT_SCALE)
    if not Decimal(0) <= coverage <= Decimal(1):
        raise DomainError("invalid_coverage", "Coverage must be between zero and one.", 422)
    if source.status not in {"source_provided", "estimated", "partial", "manual"}:
        raise DomainError("invalid_nutrition_status", "Nutrition status is invalid.", 422)

    def scaled(field: str, scale: Decimal) -> Decimal | None:
        value = getattr(source.macros, field)
        return quantize_decimal(value * basis, scale) if value is not None else None

    return MealNutritionSnapshotValue(
        recipe_id=source.recipe_id,
        estimate_id=source.estimate_id,
        recipe_title=source.recipe_title,
        basis_servings=basis,
        calories_kcal=scaled("calories_kcal", DISPLAY_CALORIE_SCALE),
        protein_g=scaled("protein_g", DISPLAY_MACRO_SCALE),
        carbohydrate_g=scaled("carbohydrate_g", DISPLAY_MACRO_SCALE),
        fat_g=scaled("fat_g", DISPLAY_MACRO_SCALE),
        status=source.status,
        coverage_ratio=coverage,
    )


def refresh_snapshot(
    previous: MealNutritionSnapshotValue,
    source: SnapshotSource,
    servings: Decimal,
) -> MealNutritionSnapshotValue:
    del previous  # The immutable prior snapshot remains available to detached history.
    return create_snapshot(source, servings)
