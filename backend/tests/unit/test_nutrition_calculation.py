from decimal import Decimal

import pytest

from cookfully.domain.common import DomainError
from cookfully.domain.nutrition import (
    IngredientNutrition,
    MacroValues,
    NutritionCorrectionValue,
    provisional_macro_range,
    resolved_macros,
    rollup_per_serving,
)


def test_six_decimal_rollup_positive_three_decimal_servings_and_null_zero() -> None:
    contributions = [
        IngredientNutrition(
            macros=MacroValues(Decimal("200"), Decimal("40"), Decimal("0"), Decimal("4")),
            matched=True,
        ),
        IngredientNutrition(
            macros=MacroValues(None, None, None, None),
            matched=False,
        ),
    ]
    estimate = rollup_per_serving(contributions, Decimal("2.000"), coverage=Decimal("0.500000"))
    assert estimate.macros.calories_kcal == Decimal("100.000000")
    assert estimate.macros.carbohydrate_g == Decimal("0.000000")
    assert estimate.macros.fat_g == Decimal("2.000000")
    assert estimate.coverage == Decimal("0.500000")
    with pytest.raises(DomainError, match="greater than zero"):
        rollup_per_serving(contributions, Decimal("0.000"), coverage=Decimal("0.5"))


def test_manual_correction_precedence_and_round_half_up_display() -> None:
    automatic = MacroValues(Decimal("99.5"), Decimal("10.04"), Decimal("20.05"), None)
    corrections = {
        "protein_g": NutritionCorrectionValue(Decimal("12.345678"), active=True),
        "fat_g": NutritionCorrectionValue(Decimal("3"), active=False),
    }
    resolved = resolved_macros(automatic, corrections)
    assert resolved.values.protein_g == Decimal("12.345678")
    assert resolved.values.fat_g is None
    assert resolved.sources["protein_g"] == "manual"
    assert resolved.display == {
        "caloriesKcal": "100",
        "proteinG": "12.3",
        "carbohydrateG": "20.1",
        "fatG": None,
    }


def test_provisional_macro_range_uses_candidate_values_without_calling_them_confirmed() -> None:
    values = provisional_macro_range(
        [
            MacroValues(Decimal("100"), Decimal("20"), Decimal("5"), Decimal("2")),
            MacroValues(Decimal("140"), Decimal("30"), Decimal("4"), Decimal("6")),
            MacroValues(Decimal("120"), Decimal("25"), Decimal("7"), Decimal("4")),
        ]
    )

    assert values.representative.calories_kcal == Decimal("120.000000")
    assert values.minimum.protein_g == Decimal("20.000000")
    assert values.maximum.protein_g == Decimal("30.000000")


def test_rollup_includes_provisional_contribution_but_keeps_coverage_separate() -> None:
    estimate = rollup_per_serving(
        [
            IngredientNutrition(
                MacroValues(Decimal("120"), Decimal("25"), Decimal("7"), Decimal("4")),
                matched=False,
                provisional=True,
            )
        ],
        Decimal("1.000"),
        coverage=Decimal("0.000000"),
    )

    assert estimate.macros.protein_g == Decimal("25.000000")
    assert estimate.coverage == Decimal("0.000000")
