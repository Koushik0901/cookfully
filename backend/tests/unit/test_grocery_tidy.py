from __future__ import annotations

from typing import Any

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.grocery_tidy import classify, synonym_map
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore

SAME = {"green onion": "scallion", "scallion": "green onion"}


def _engine(responder: Any) -> Decisions:
    return Decisions(
        DecisionsConfig("k", features={Purpose.GROCERY_TIDY: FeatureConfig(True, ("m1", "m2"))}),
        ScriptedDecisionTransport(responder),
        InMemoryDecisionStore(),
    )


def _merge_responder(model: str, state: Any, questions: Any) -> object:
    criteria = questions["same"]["criteria"]
    name = state["grocery_item"]
    match = SAME.get(name)
    key = next((k for k, v in criteria.items() if v == match), "none")
    return {
        "same": {
            "type": "choice",
            "probabilities": {key: 0.95, "none": 0.05} if key != "none" else {"none": 1.0},
        }
    }


def test_agreed_synonyms_merge_onto_the_alphabetically_first_name() -> None:
    mapping = synonym_map(
        _engine(_merge_responder), ["scallion", "green onion", "rice", "scallion"]
    )
    assert mapping == {"scallion": "green onion"}


def test_vetoes_and_disagreement_prevent_merges() -> None:
    engine = _engine(_merge_responder)
    assert (
        synonym_map(engine, ["scallion", "green onion"], {"green onion": frozenset({"scallion"})})
        == {}
    )

    def split(model: str, state: Any, questions: Any) -> object:
        return (
            _merge_responder(model, state, questions)
            if model == "m1"
            else {"same": {"type": "choice", "probabilities": {"none": 1.0}}}
        )

    assert synonym_map(_engine(split), ["scallion", "green onion"]) == {}
    assert synonym_map(_engine(lambda *_a: None), ["scallion", "green onion"]) == {}
    assert synonym_map(engine, ["rice"]) == {}


def test_classify_assigns_confident_aisles_and_staples() -> None:
    def responder(_model: str, state: Any, _q: Any) -> object:
        salt = state["grocery_item"] == "salt"
        return {
            "aisle": {
                "type": "choice",
                "probabilities": {"spices": 0.9, "other": 0.1}
                if salt
                else {"produce": 0.4, "other": 0.35, "pantry": 0.25},
            },
            "staple": {"type": "noul", "noul": 0.95 if salt else 0.1},
        }

    labels = classify(_engine(responder), ["salt", "dragon fruit"])
    assert labels["salt"].aisle == "spices" and labels["salt"].staple is True
    assert labels["dragon fruit"].aisle is None and labels["dragon fruit"].staple is False
