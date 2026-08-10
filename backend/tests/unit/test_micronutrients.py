from __future__ import annotations

from decimal import Decimal

from vigor_vine.domain.nutrition import (
    MICRONUTRIENT_KEYS,
    USDA_MICRONUTRIENT_MANIFEST,
    MicronutrientContribution,
    SourceMicronutrient,
    resolve_micronutrients,
    rollup_micronutrients_per_serving,
)


def test_manifest_has_exactly_nine_canonical_fields_units_and_versioned_usda_ids() -> None:
    assert MICRONUTRIENT_KEYS == (
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
    assert tuple(USDA_MICRONUTRIENT_MANIFEST) == MICRONUTRIENT_KEYS
    assert {entry.unit for entry in USDA_MICRONUTRIENT_MANIFEST.values()} == {"g", "mg", "ug"}
    assert all(entry.fdc_nutrient_id > 0 for entry in USDA_MICRONUTRIENT_MANIFEST.values())
    assert all(entry.mapping_version.startswith("usda-fdc-") for entry in USDA_MICRONUTRIENT_MANIFEST.values())


def test_missing_is_null_but_explicit_source_zero_is_preserved_with_provenance() -> None:
    resolved = resolve_micronutrients(
        {
            "sodium_mg": SourceMicronutrient(
                Decimal("0"),
                source="USDA FoodData Central Foundation",
                source_release="2026-04",
                explicit=True,
            )
        },
        mass_coverage=Decimal("1"),
        count_coverage=Decimal("1"),
        input_hash="abc123",
    )
    assert resolved["dietary_fiber_g"].value is None
    assert resolved["dietary_fiber_g"].explicit_zero is False
    assert resolved["sodium_mg"].value == Decimal("0.000000")
    assert resolved["sodium_mg"].explicit_zero is True
    assert resolved["sodium_mg"].source_release == "2026-04"
    assert resolved["sodium_mg"].input_hash == "abc123"


def test_coverage_uses_lower_of_mass_and_count_and_insufficient_values_are_null() -> None:
    resolved = resolve_micronutrients(
        {"iron_mg": SourceMicronutrient(Decimal("3.25"), source="USDA", source_release="2026-04")},
        mass_coverage=Decimal("0.950000"),
        count_coverage=Decimal("0.800000"),
        input_hash="coverage",
    )
    assert resolved["iron_mg"].coverage_ratio == Decimal("0.800000")
    assert resolved["iron_mg"].value is None
    assert "coverage" in (resolved["iron_mg"].assumption or "")


def test_rollup_is_six_decimal_per_serving_and_propagates_provenance() -> None:
    rolled = rollup_micronutrients_per_serving(
        (
            MicronutrientContribution(
                {
                    "calcium_mg": SourceMicronutrient(
                        Decimal("120.000000"), source="USDA", source_release="2026-04"
                    ),
                    "vitamin_c_mg": SourceMicronutrient(
                        Decimal("0"), source="USDA", source_release="2026-04", explicit=True
                    ),
                },
                mass_grams=Decimal("100"),
                resolved=True,
            ),
            MicronutrientContribution(
                {"calcium_mg": SourceMicronutrient(Decimal("30"), source="USDA", source_release="2026-04")},
                mass_grams=Decimal("50"),
                resolved=True,
            ),
        ),
        servings=Decimal("3"),
        total_convertible_mass=Decimal("150"),
        total_ingredient_count=2,
        input_hash="rollup",
    )
    assert rolled["calcium_mg"].value == Decimal("50.000000")
    assert rolled["calcium_mg"].coverage_ratio == Decimal("1.000000")
    assert rolled["vitamin_c_mg"].value == Decimal("0.000000")
    assert rolled["vitamin_c_mg"].explicit_zero is True
