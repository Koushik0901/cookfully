from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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

MicronutrientKey = Literal[
    "dietary_fiber_g",
    "sodium_mg",
    "potassium_mg",
    "calcium_mg",
    "iron_mg",
    "magnesium_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
    "vitamin_b12_ug",
]
MicronutrientAmounts = dict[MicronutrientKey, Decimal | None]

MICRONUTRIENT_KEYS: tuple[MicronutrientKey, ...] = (
    "dietary_fiber_g",
    "sodium_mg",
    "potassium_mg",
    "calcium_mg",
    "iron_mg",
    "magnesium_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
    "vitamin_b12_ug",
)

MICRONUTRIENT_MINIMUM_COVERAGE = Decimal("0.900000")


@dataclass(frozen=True, slots=True)
class UsdaMicronutrientMapping:
    key: MicronutrientKey
    fdc_nutrient_id: int
    legacy_number: str
    unit: Literal["g", "mg", "ug"]
    mapping_version: str


_MAPPING_VERSION = "usda-fdc-2026-04-v1"
USDA_MICRONUTRIENT_MANIFEST: dict[MicronutrientKey, UsdaMicronutrientMapping] = {
    value.key: value
    for value in (
        UsdaMicronutrientMapping("dietary_fiber_g", 1079, "291", "g", _MAPPING_VERSION),
        UsdaMicronutrientMapping("sodium_mg", 1093, "307", "mg", _MAPPING_VERSION),
        UsdaMicronutrientMapping("potassium_mg", 1092, "306", "mg", _MAPPING_VERSION),
        UsdaMicronutrientMapping("calcium_mg", 1087, "301", "mg", _MAPPING_VERSION),
        UsdaMicronutrientMapping("iron_mg", 1089, "303", "mg", _MAPPING_VERSION),
        UsdaMicronutrientMapping("magnesium_mg", 1090, "304", "mg", _MAPPING_VERSION),
        UsdaMicronutrientMapping("vitamin_c_mg", 1162, "401", "mg", _MAPPING_VERSION),
        UsdaMicronutrientMapping("vitamin_d_ug", 1114, "328", "ug", _MAPPING_VERSION),
        UsdaMicronutrientMapping("vitamin_b12_ug", 1178, "418", "ug", _MAPPING_VERSION),
    )
}


def usda_micronutrient_mapping(code: str | int) -> UsdaMicronutrientMapping | None:
    normalized = str(code).strip()
    return next(
        (
            item
            for item in USDA_MICRONUTRIENT_MANIFEST.values()
            if normalized in {str(item.fdc_nutrient_id), item.legacy_number}
        ),
        None,
    )


@dataclass(frozen=True, slots=True)
class SourceMicronutrient:
    value: Decimal
    source: str
    source_release: str
    explicit: bool = False


@dataclass(frozen=True, slots=True)
class SupportedMicronutrientValue:
    key: MicronutrientKey
    value: Decimal | None
    unit: str
    explicit_zero: bool
    source: str | None
    source_release: str | None
    mapping_version: str
    fdc_nutrient_id: int
    input_hash: str
    coverage_ratio: Decimal
    assumption: str | None = None
    calculated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MicronutrientContribution:
    values: dict[MicronutrientKey, SourceMicronutrient]
    mass_grams: Decimal | None
    resolved: bool


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


def resolve_micronutrients(
    source_values: dict[MicronutrientKey, SourceMicronutrient],
    *,
    mass_coverage: Decimal,
    count_coverage: Decimal,
    input_hash: str,
    calculated_at: datetime | None = None,
) -> dict[MicronutrientKey, SupportedMicronutrientValue]:
    coverage = quantize_decimal(min(mass_coverage, count_coverage), NUTRIENT_SCALE)
    if not Decimal(0) <= coverage <= Decimal(1):
        raise DomainError("invalid_coverage", "Coverage must be between zero and one.", 422)
    result: dict[MicronutrientKey, SupportedMicronutrientValue] = {}
    for key in MICRONUTRIENT_KEYS:
        mapping = USDA_MICRONUTRIENT_MANIFEST[key]
        source = source_values.get(key)
        assumption: str | None = None
        value: Decimal | None = None
        explicit_zero = False
        if coverage < MICRONUTRIENT_MINIMUM_COVERAGE:
            assumption = (
                "Unavailable because nutrient coverage is below the 0.900000 safety threshold."
            )
        elif source is None:
            assumption = "Unavailable because the active source has no explicit nutrient value."
        elif source.value < 0:
            raise DomainError(
                "micronutrient_negative", "Micronutrient values cannot be negative.", 422
            )
        elif source.value == 0 and not source.explicit:
            assumption = "Unavailable because zero was not explicit in the source record."
        else:
            value = quantize_decimal(source.value, NUTRIENT_SCALE)
            explicit_zero = value == 0 and source.explicit
        result[key] = SupportedMicronutrientValue(
            key=key,
            value=value,
            unit=mapping.unit,
            explicit_zero=explicit_zero,
            source=source.source if source is not None else None,
            source_release=source.source_release if source is not None else None,
            mapping_version=mapping.mapping_version,
            fdc_nutrient_id=mapping.fdc_nutrient_id,
            input_hash=input_hash,
            coverage_ratio=coverage,
            assumption=assumption,
            calculated_at=calculated_at,
        )
    return result


def rollup_micronutrients_per_serving(
    contributions: tuple[MicronutrientContribution, ...],
    *,
    servings: Decimal,
    total_convertible_mass: Decimal,
    total_ingredient_count: int,
    input_hash: str,
    calculated_at: datetime | None = None,
) -> dict[MicronutrientKey, SupportedMicronutrientValue]:
    serving_value = quantize_decimal(servings, SERVING_SCALE)
    if serving_value <= 0:
        raise DomainError("invalid_servings", "Serving quantity must be greater than zero.", 422)
    if total_convertible_mass < 0 or total_ingredient_count < 0:
        raise DomainError("invalid_coverage_basis", "Coverage bases cannot be negative.", 422)

    result: dict[MicronutrientKey, SupportedMicronutrientValue] = {}
    for key in MICRONUTRIENT_KEYS:
        present = [item for item in contributions if item.resolved and key in item.values]
        resolved_mass = sum(
            (item.mass_grams for item in present if item.mass_grams is not None), Decimal(0)
        )
        mass_coverage = (
            resolved_mass / total_convertible_mass if total_convertible_mass > 0 else Decimal(0)
        )
        count_coverage = (
            Decimal(len(present)) / Decimal(total_ingredient_count)
            if total_ingredient_count > 0
            else Decimal(0)
        )
        values = [item.values[key] for item in present]
        source_value: SourceMicronutrient | None = None
        if values:
            total = sum((item.value for item in values), Decimal(0)) / serving_value
            releases = sorted({item.source_release for item in values})
            sources = sorted({item.source for item in values})
            source_value = SourceMicronutrient(
                total,
                source="; ".join(sources),
                source_release="; ".join(releases),
                explicit=all(item.explicit for item in values),
            )
        result[key] = resolve_micronutrients(
            {key: source_value} if source_value is not None else {},
            mass_coverage=mass_coverage,
            count_coverage=count_coverage,
            input_hash=input_hash,
            calculated_at=calculated_at,
        )[key]
    return result
