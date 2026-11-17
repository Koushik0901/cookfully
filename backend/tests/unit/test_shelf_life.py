from __future__ import annotations

from typing import Any

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.shelf_life import estimate_days
from cookfully.domain.decisions import Purpose
from cookfully.domain.expiry_lifespans import needs_model_estimate
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore


def _engine(responder: Any) -> tuple[Decisions, list[Any]]:
    calls: list[Any] = []

    def respond(model: str, state: Any, questions: Any) -> object:
        calls.append(dict(state))
        return responder(model, state, questions)

    engine = Decisions(
        DecisionsConfig("k", features={Purpose.SHELF_LIFE: FeatureConfig(True, ("m1", "m2"))}),
        ScriptedDecisionTransport(respond),
        InMemoryDecisionStore(),
    )
    return engine, calls


def _choice(probabilities: dict[str, float]) -> object:
    return {"lifespan": {"type": "choice", "probabilities": probabilities}}


def test_only_items_the_table_and_label_rule_do_not_cover_need_a_model() -> None:
    assert needs_model_estimate("kimchi")
    assert not needs_model_estimate("tomatoes")  # in the lifespan table
    assert not needs_model_estimate("whole milk")  # needs the label date


def test_an_agreed_bucket_becomes_days_and_repeat_names_are_cached() -> None:
    engine, calls = _engine(lambda _m, _s, _q: _choice({"month": 0.8, "week": 0.2}))
    assert estimate_days(engine, "Kimchi") == 30
    assert estimate_days(engine, "  kimchi ") == 30
    assert len(calls) == 2  # one per model, then served from the cache
    assert calls[0] == {"pantry_item": "kimchi"}


def test_disagreement_low_confidence_or_no_answer_gives_no_date() -> None:
    split, _ = _engine(
        lambda model, _s, _q: _choice({"month": 0.9} if model == "m1" else {"week": 0.9})
    )
    assert estimate_days(split, "kimchi") is None
    unsure, _ = _engine(lambda _m, _s, _q: _choice({"month": 0.4, "week": 0.35, "months": 0.25}))
    assert estimate_days(unsure, "kimchi") is None
    down, _ = _engine(lambda _m, _s, _q: None)
    assert estimate_days(down, "kimchi") is None


def test_table_items_never_ask() -> None:
    engine, calls = _engine(lambda _m, _s, _q: _choice({"month": 1.0}))
    assert estimate_days(engine, "tomato") is None
    assert calls == []
