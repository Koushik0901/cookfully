from __future__ import annotations

from decimal import Decimal

import pytest

from vigor_vine.application.pantry import (
    PantryQuantity,
    apply_quantity_deduction,
    convert_quantity,
    match_food_name,
    normalize_pantry_name,
    reverse_quantity_deduction,
)
from vigor_vine.domain.common import DomainError


def test_normalization_and_conversion_preserve_six_decimal_precision() -> None:
    assert normalize_pantry_name("  Crème-Fraîche (Light)  ") == "creme fraiche light"
    assert convert_quantity(Decimal("0.750000"), "kg", "g") == Decimal("750.000000")
    assert convert_quantity(Decimal("1.2345674"), "l", "ml") == Decimal("1234.567400")
    assert convert_quantity(Decimal("2"), "each", "count") == Decimal("2.000000")


def test_conversion_rejects_cross_dimension_and_unknown_units() -> None:
    with pytest.raises(DomainError, match="compatible"):
        convert_quantity(Decimal("250"), "g", "ml")
    with pytest.raises(DomainError, match="supported"):
        convert_quantity(Decimal("1"), "cup", "g")


def test_match_confidence_is_explicit_and_ambiguous_results_are_not_automatic() -> None:
    exact = match_food_name("Chicken Breast", (("food-1", "chicken breast"),))
    assert exact.reference_id == "food-1"
    assert exact.status == "matched"
    assert exact.confidence == Decimal("1.000000")

    ambiguous = match_food_name(
        "chicken",
        (("food-1", "chicken breast"), ("food-2", "chicken thigh")),
    )
    assert ambiguous.reference_id is None
    assert ambiguous.status == "proposed"
    assert ambiguous.confidence < Decimal("1.000000")


def test_deduction_and_reversal_are_exact_and_state_guarded() -> None:
    pantry = PantryQuantity(Decimal("0.500000"), "kg", version=7)
    grocery = PantryQuantity(Decimal("300.000000"), "g", version=4)

    applied = apply_quantity_deduction(pantry, grocery)
    assert applied.pantry_after == PantryQuantity(Decimal("0.200000"), "kg", version=8)
    assert applied.grocery_after == PantryQuantity(Decimal("0.000000"), "g", version=5)
    assert applied.pantry_amount == Decimal("0.300000")
    assert applied.grocery_amount == Decimal("300.000000")

    restored_pantry, restored_grocery = reverse_quantity_deduction(
        applied,
        pantry=applied.pantry_after,
        grocery=applied.grocery_after,
    )
    assert restored_pantry == PantryQuantity(Decimal("0.500000"), "kg", version=9)
    assert restored_grocery == PantryQuantity(Decimal("300.000000"), "g", version=6)

    with pytest.raises(DomainError, match="changed"):
        reverse_quantity_deduction(
            applied,
            pantry=PantryQuantity(Decimal("0.100000"), "kg", version=9),
            grocery=applied.grocery_after,
        )
