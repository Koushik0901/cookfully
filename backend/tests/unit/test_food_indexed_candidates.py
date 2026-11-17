from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from cookfully.api.routes import foods as foods_routes
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.reference_foods import FoodReference

DIMENSIONS = 384


def _vector(first: float) -> list[float]:
    return [first] + [0.0] * (DIMENSIONS - 1)


class _FakeSession:
    """Answers the two index queries (reference foods, then owner foods) with canned rows."""

    def __init__(self, usda_rows: list[Any], owner_rows: list[Any]) -> None:
        self._answers = [usda_rows, owner_rows]

    def get(self, *_args: object) -> None:
        return None

    def execute(self, *_args: object) -> SimpleNamespace:
        rows = self._answers.pop(0)
        return SimpleNamespace(all=lambda: rows)


def _embedder(vector: list[float]) -> SimpleNamespace:
    return SimpleNamespace(embed=lambda texts: [vector for _ in texts])


def test_indexed_candidates_rank_reference_and_owner_foods_by_similarity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usda = FoodReference(
        id=uuid4(),
        description="Rice, white, raw",
        brand_owner=None,
        serving_size_g=None,
        serving_unit=None,
    )
    owner_food = OwnerFood(
        id=uuid4(),
        display_name="My rice blend",
        brand=None,
        typical_serving_g=None,
        typical_serving_unit=None,
    )
    usda_row = SimpleNamespace(embedding_vector=_vector(0.5))
    owner_row = SimpleNamespace(embedding_vector=_vector(0.9))
    monkeypatch.setattr(
        foods_routes.engine, "resolve_embedder", lambda *a, **k: _embedder(_vector(1.0))
    )
    session: Any = _FakeSession([(usda_row, usda)], [(owner_row, owner_food)])

    candidates = foods_routes._indexed_candidates(session, uuid4(), "rice")

    assert [(item.source, item.description) for item in candidates] == [
        ("owner", "My rice blend"),
        ("usda", "Rice, white, raw"),
    ]
    assert candidates[0].semantic_similarity == Decimal("0.9")


def test_indexed_candidates_are_empty_for_an_embedder_of_the_wrong_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(foods_routes.engine, "resolve_embedder", lambda *a, **k: _embedder([1.0]))
    session: Any = _FakeSession([], [])
    assert foods_routes._indexed_candidates(session, uuid4(), "rice") == []
