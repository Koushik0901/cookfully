from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from cookfully.api.routes import foods
from cookfully.application.food_match_memories import RememberedFoodChoice


def _remembered(
    monkeypatch: pytest.MonkeyPatch, choice: RememberedFoodChoice, food_name: str, query: str
) -> foods.FoodCandidateResponse | None:
    monkeypatch.setattr(foods, "remembered_food_choice_for_name", lambda *a, **kw: choice)
    session = cast(Session, None)  # the lookup is stubbed, so the session is never used
    return foods._remembered_candidate_for_name(session, uuid4(), food_name, query=query)


def _usda(description: str) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        description=description,
        brand_owner=None,
        serving_size_g=Decimal("100"),
        serving_unit="g",
    )


def test_a_remembered_usda_food_is_offered_first_and_marked_remembered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _usda("Chicken, breast, raw")

    candidate = _remembered(
        monkeypatch, RememberedFoodChoice(food_reference=reference), "chicken breast", "chicken"
    )

    assert candidate is not None
    assert (candidate.source, candidate.id, candidate.remembered) == ("usda", reference.id, True)
    assert candidate.description == "Chicken, breast, raw"


def test_nothing_remembered_offers_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _remembered(monkeypatch, RememberedFoodChoice(), "chicken", "chicken") is None
