from __future__ import annotations

from decimal import Decimal

import pytest

from cookfully.application.pantry import (
    PantryQuantity,
    apply_quantity_deduction,
    convert_quantity,
    normalize_pantry_name,
    reverse_quantity_deduction,
)
from cookfully.domain.common import DomainError
from cookfully.domain.ingredient_nutrition.matching import FoodCandidate, MatchDecision


def test_normalization_and_conversion_preserve_six_decimal_precision() -> None:
    assert normalize_pantry_name("  Crème-Fraîche (Light)  ") == "creme fraiche light"
    assert convert_quantity(Decimal("0.750000"), "kg", "g") == Decimal("750.000000")
    assert convert_quantity(Decimal("1.2345674"), "l", "ml") == Decimal("1234.567400")
    assert convert_quantity(Decimal("2"), "each", "count") == Decimal("2.000000")


def test_conversion_rejects_cross_dimension_and_unknown_units() -> None:
    with pytest.raises(DomainError, match="compatible"):
        convert_quantity(Decimal("250"), "g", "ml")
    with pytest.raises(DomainError, match="compatible"):
        convert_quantity(Decimal("1"), "cup", "g")
    with pytest.raises(DomainError, match="supported"):
        convert_quantity(Decimal("1"), "stone", "g")


def _candidate(score: str, external_id: str = "food-1"):
    from cookfully.domain.common import uuid7
    from cookfully.infrastructure.models.reference_foods import FoodReference

    food = FoodReference(
        id=uuid7(),
        dataset_id=uuid7(),
        external_id=external_id,
        description="Cherry tomatoes, raw",
        normalized_name="cherry tomato",
        data_type="sr_legacy",
        basis_grams=100,
    )
    return FoodCandidate(food, Decimal(score))


def test_resolve_match_maps_engine_decisions(monkeypatch) -> None:
    from cookfully.application import pantry

    decision = MatchDecision("matched", "ranked", _candidate("0.850000"), ())
    fake = type("E", (), {"match_ingredient": lambda self, session, name, **kw: decision})()
    monkeypatch.setattr(pantry, "engine", fake)
    reference_id, owner_food_id, status, confidence = pantry.PantryService._resolve_match(
        None, None, "cherry tomatoes", None, None
    )
    assert owner_food_id is None
    assert status == "matched"
    assert confidence == Decimal("0.850000")
    assert reference_id is not None


def test_resolve_match_proposes_ambiguous_top_alternative(monkeypatch) -> None:
    from cookfully.application import pantry

    top = _candidate("0.700000")
    decision = MatchDecision("ambiguous", "ranked", None, (top,))
    fake = type("E", (), {"match_ingredient": lambda self, session, name, **kw: decision})()
    monkeypatch.setattr(pantry, "engine", fake)
    reference_id, owner_food_id, status, confidence = pantry.PantryService._resolve_match(
        None, None, "tomato", None, None
    )
    assert owner_food_id is None
    assert status == "proposed"
    assert confidence == Decimal("0.700000")
    assert reference_id == top.food.id


def test_resolve_match_unmatched_has_no_reference_or_confidence(monkeypatch) -> None:
    from cookfully.application import pantry

    decision = MatchDecision("unmatched", "ranked", None, ())
    fake = type("E", (), {"match_ingredient": lambda self, session, name, **kw: decision})()
    monkeypatch.setattr(pantry, "engine", fake)
    reference_id, owner_food_id, status, confidence = pantry.PantryService._resolve_match(
        None, None, "mystery item", None, None
    )
    assert (reference_id, owner_food_id, status, confidence) == (None, None, "unmatched", None)


def test_resolve_match_never_loads_a_model_for_an_automatic_pantry_add(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from cookfully.application import pantry

    session = MagicMock()
    monkeypatch.setattr(
        pantry,
        "engine",
        type(
            "E",
            (),
            {"match_ingredient": lambda *_args, **_kwargs: pytest.fail("must not load model")},
        )(),
    )
    assert pantry.PantryService._resolve_match(session, None, "rice", None, None) == (
        None,
        None,
        "unmatched",
        None,
    )


def test_resolve_match_manual_selection_pins_confidence(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from cookfully.application import pantry
    from cookfully.domain.common import uuid7

    food_id = uuid7()
    session = MagicMock()
    session.get.return_value = object()

    def fail(self, session, name, **kwargs):
        raise AssertionError("engine must not be consulted for manual selection")

    monkeypatch.setattr(pantry, "engine", type("E", (), {"match_ingredient": fail})())
    reference_id, owner_food_id, status, confidence = pantry.PantryService._resolve_match(
        session, None, "anything", food_id, None
    )
    session.get.assert_called_once()
    assert (reference_id, owner_food_id, status, confidence) == (
        food_id,
        None,
        "manual",
        Decimal("1.000000"),
    )


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
