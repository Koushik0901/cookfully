from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.substitutions import suggest
from cookfully.domain.decisions import Purpose
from cookfully.domain.substitutions import TABLE, Substitute, rank, table_key
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore

D = Decimal


@pytest.mark.parametrize(
    ("line", "key"),
    [
        ("1 cup buttermilk", "buttermilk"),
        ("2 tbsp butter, melted", "butter"),
        ("2 large eggs", "egg"),
        ("1/2 cup sour cream", "sour cream"),
        ("1 cup low-fat milk", "milk"),
        ("2 tbsp peanut butter", None),
        ("1 can coconut milk", None),
        ("1 tsp salt", None),
        ("3 tbsp soy sauce", "soy sauce"),
    ],
)
def test_lines_map_to_the_most_specific_table_entry(line: str, key: str | None) -> None:
    assert table_key(line) == key


def test_rank_orders_by_probability_and_hides_unlikely_swaps() -> None:
    a, b, c = Substitute("A", "1"), Substitute("B", "1"), Substitute("C", "1")
    ranked = rank([a, b, c], [D("0.6"), D("0.9"), D("0.2")])
    assert [(r.substitute.name, r.probability) for r in ranked] == [
        ("B", D("0.9")),
        ("A", D("0.6")),
    ]
    unranked = rank([a, b], [None, None])
    assert [(r.substitute.name, r.probability) for r in unranked] == [("A", None), ("B", None)]


def _engine(responder: Any) -> Decisions:
    return Decisions(
        DecisionsConfig("k", features={Purpose.SUBSTITUTIONS: FeatureConfig(True, ("m1", "m2"))}),
        ScriptedDecisionTransport(responder),
        InMemoryDecisionStore(),
    )


def test_suggest_asks_one_question_per_table_candidate_in_recipe_context() -> None:
    seen: list[dict[str, str]] = []

    def responder(_model: str, state: Any, _q: Any) -> object:
        seen.append(dict(state))
        works = 0.9 if state["substitute"].startswith("Milk with lemon") else 0.3
        return {"works": {"type": "noul", "noul": works}}

    result = suggest(
        _engine(responder),
        recipe_title="Pancakes",
        ingredients=["1 cup flour", "1 cup buttermilk"],
        steps=["Whisk and fry."],
        ingredient_id=uuid4(),
        line="1 cup buttermilk",
    )
    assert result.key == "buttermilk"
    assert result.ranked is True
    assert [r.substitute.name for r in result.substitutes] == ["Milk with lemon juice or vinegar"]
    assert len({s["substitute"] for s in seen}) == len(TABLE["buttermilk"])
    assert seen[0]["recipe"] == "Pancakes" and seen[0]["original_line"] == "1 cup buttermilk"


def test_without_answers_the_table_is_returned_unranked() -> None:
    result = suggest(
        _engine(lambda _m, _s, _q: None),
        recipe_title="R",
        ingredients=[],
        steps=[],
        ingredient_id=uuid4(),
        line="2 eggs",
    )
    assert result.ranked is False
    assert [r.substitute for r in result.substitutes] == list(TABLE["egg"])


def test_lines_without_a_table_entry_get_nothing_and_ask_nothing() -> None:
    calls: list[object] = []
    result = suggest(
        _engine(lambda *_a: calls.append(1)),
        recipe_title="R",
        ingredients=[],
        steps=[],
        ingredient_id=uuid4(),
        line="1 tsp salt",
    )
    assert result.substitutes == () and calls == []
