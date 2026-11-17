from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.hidden_ingredients import (
    CHECKED,
    NOT_CHECKED,
    HiddenLine,
    check_hidden,
)
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore

WORCESTERSHIRE = HiddenLine(uuid4(), "2 tbsp Worcestershire sauce")
OIL = HiddenLine(uuid4(), "1 tbsp olive oil")


def _engine(responder: Any, models: tuple[str, ...] = ("m1", "m2")) -> tuple[Decisions, list[Any]]:
    calls: list[Any] = []

    def respond(model: str, state: Any, questions: Any) -> object:
        calls.append((model, dict(state), dict(questions)))
        return responder(model, state, questions)

    engine = Decisions(
        DecisionsConfig("k", features={Purpose.HIDDEN_INGREDIENTS: FeatureConfig(True, models)}),
        ScriptedDecisionTransport(respond),
        InMemoryDecisionStore(),
    )
    return engine, calls


def _noul(values: dict[str, float]) -> Any:
    return {key: {"type": "noul", "noul": value} for key, value in values.items()}


def test_flags_suspected_items_using_the_most_cautious_model() -> None:
    def responder(model: str, state: Any, questions: Any) -> object:
        if "Worcestershire" in state["ingredient_line"]:
            # m1 is unsure about fish, m2 is fairly sure: the worst case wins.
            return _noul({"a0": 0.3 if model == "m1" else 0.85, "a1": 0.05})
        return _noul({"a0": 0.02, "a1": 0.01})

    engine, calls = _engine(responder)
    result = check_hidden(
        engine, recipe_title="Caesar", lines=[WORCESTERSHIRE, OIL], avoid=["fish", "peanuts"]
    )
    assert result.status == CHECKED
    assert [(f.ingredient_id, f.item, f.source, f.probability) for f in result.flags] == [
        (WORCESTERSHIRE.ingredient_id, "fish", "model", Decimal("0.85"))
    ]
    # One request per line per model, every avoid item asked in it.
    assert len(calls) == 4
    assert set(calls[0][2]) == {"a0", "a1"}
    assert "fish" in calls[0][2]["a0"]["instructions"]


def test_pairs_already_named_in_the_line_are_not_asked() -> None:
    engine, calls = _engine(lambda _m, _s, _q: _noul({"a1": 0.9}), models=("m1",))
    result = check_hidden(
        engine,
        recipe_title="Caesar",
        lines=[WORCESTERSHIRE],
        avoid=["fish", "dairy"],
        already=frozenset({(WORCESTERSHIRE.ingredient_id, "fish")}),
    )
    assert set(calls[0][2]) == {"a1"}
    assert [flag.item for flag in result.flags] == ["dairy"]


def test_any_missing_answer_means_not_checked() -> None:
    engine, _ = _engine(lambda _m, _s, _q: None)
    result = check_hidden(engine, recipe_title="R", lines=[OIL], avoid=["fish"])
    assert result.status == NOT_CHECKED
    assert result.flags == ()


def test_nothing_to_ask_is_checked_without_calls() -> None:
    engine, calls = _engine(lambda _m, _s, _q: None)
    assert check_hidden(engine, recipe_title="R", lines=[], avoid=["fish"]).status == CHECKED
    assert calls == []
