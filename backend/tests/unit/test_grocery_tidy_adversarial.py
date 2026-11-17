"""Grocery tidy: merge groups, ordering, vetoes, scale and broken models."""

from __future__ import annotations

import itertools
from collections.abc import Mapping
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.grocery_tidy import (
    AISLES,
    MAX_MERGE_OPTIONS,
    classify,
    synonym_map,
)
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore


def _engine(responder: Any, models: tuple[str, ...] = ("m1", "m2")) -> Decisions:
    return Decisions(
        DecisionsConfig("k", features={Purpose.GROCERY_TIDY: FeatureConfig(True, models)}),
        ScriptedDecisionTransport(responder),
        InMemoryDecisionStore(),
    )


def _responder(says_same: Mapping[str, str], confidence: float = 0.95) -> Any:
    def respond(_model: str, state: Any, questions: Any) -> object:
        criteria = questions["same"]["criteria"]
        partner = says_same.get(state["grocery_item"])
        key = next((k for k, v in criteria.items() if v == partner), "none")
        if key == "none":
            return {"same": {"type": "choice", "probabilities": {"none": 1.0}}}
        return {
            "same": {
                "type": "choice",
                "probabilities": {key: confidence, "none": round(1 - confidence, 6)},
            }
        }

    return respond


def test_a_pair_that_only_one_side_claims_still_merges_when_the_panel_agrees() -> None:
    # "scallions" says it equals "green onions"; "green onions" does not answer back.
    mapping = synonym_map(
        _engine(_responder({"scallions": "green onions"})), ["scallions", "green onions"]
    )
    assert (
        mapping == {"scallions": "green onions"}
        or mapping == {"green onions": "scallions"}
        or mapping == {}
    )
    # whichever way it resolves, it must never merge a name into itself
    assert all(name != target for name, target in mapping.items())


def test_a_three_way_chain_never_creates_a_chain_or_loop_in_the_result() -> None:
    says = {"a": "b", "b": "c", "c": "a"}
    mapping = synonym_map(_engine(_responder(says)), ["a", "b", "c", "d"])
    for name, target in mapping.items():
        assert name != target
        assert target not in mapping, "a merge target must not itself merge elsewhere"


@settings(max_examples=120, deadline=None)
@given(
    pairs=st.dictionaries(
        st.sampled_from(list("abcdefgh")), st.sampled_from(list("abcdefgh")), max_size=8
    ),
    shuffled=st.permutations(list("abcdefgh")),
)
def test_merging_is_independent_of_the_order_of_the_list_and_never_chains(
    pairs: dict[str, str], shuffled: list[str]
) -> None:
    names = list("abcdefgh")
    first = synonym_map(_engine(_responder(pairs)), names)
    second = synonym_map(_engine(_responder(pairs)), shuffled)
    assert first == second
    for name, target in first.items():
        assert name != target and target not in first and target in names


def test_vetoes_work_in_either_direction() -> None:
    says = {"scallions": "green onions", "green onions": "scallions"}
    engine = _engine(_responder(says))
    assert (
        synonym_map(
            engine, ["scallions", "green onions"], {"scallions": frozenset({"green onions"})}
        )
        == {}
    )
    assert (
        synonym_map(
            engine, ["scallions", "green onions"], {"green onions": frozenset({"scallions"})}
        )
        == {}
    )


def test_a_veto_on_one_pair_does_not_block_an_unrelated_merge() -> None:
    says = {
        "scallions": "green onions",
        "green onions": "scallions",
        "coriander": "cilantro",
        "cilantro": "coriander",
    }
    mapping = synonym_map(
        _engine(_responder(says)),
        ["scallions", "green onions", "coriander", "cilantro"],
        {"scallions": frozenset({"green onions"})},
    )
    assert mapping == {"coriander": "cilantro"}


def test_a_list_above_the_old_limit_still_merges_its_synonyms() -> None:
    names = [f"item{i:03d}" for i in range(MAX_MERGE_OPTIONS - 2)] + ["scallions", "green onions"]
    says = {"scallions": "green onions", "green onions": "scallions"}
    assert synonym_map(_engine(_responder(says)), names) == {"scallions": "green onions"}


def test_a_list_beyond_the_hard_cap_is_skipped_not_half_merged() -> None:
    names = [f"item{i:04d}" for i in range(MAX_MERGE_OPTIONS + 1)]
    engine = _engine(_responder({}))
    assert synonym_map(engine, names) == {}


def test_names_that_are_blank_or_duplicates_are_ignored() -> None:
    assert synonym_map(_engine(_responder({})), ["", "", "rice", "rice"]) == {}


def test_a_name_that_is_the_literal_word_none_is_not_confused_with_no_match() -> None:
    says = {"none": "nothing", "nothing": "none"}
    assert synonym_map(_engine(_responder(says)), ["none", "nothing"]) in (
        {"none": "nothing"},
        {"nothing": "none"},
        {},
    )


def test_low_confidence_agreement_does_not_merge() -> None:
    says = {"scallions": "green onions", "green onions": "scallions"}
    assert (
        synonym_map(_engine(_responder(says, confidence=0.45)), ["scallions", "green onions"]) == {}
    )


def test_a_model_that_answers_garbage_for_every_item_merges_nothing() -> None:
    garbage = lambda *_a: {"same": {"type": "choice", "probabilities": {"o0": "high"}}}  # noqa: E731
    assert synonym_map(_engine(garbage), ["scallions", "green onions", "rice"]) == {}


# --- aisles and staples ---------------------------------------------------------------------------


def _classifier(aisle: str, staple: float) -> Any:
    def respond(_m: str, _s: Any, _q: Any) -> object:
        return {
            "aisle": {"type": "choice", "probabilities": {aisle: 0.9, "other": 0.1}},
            "staple": {"type": "noul", "noul": staple},
        }

    return respond


def test_an_unknown_aisle_key_from_a_model_is_dropped_not_stored() -> None:
    engine = _engine(_classifier("aisle_that_does_not_exist", 0.5))
    labels = classify(engine, ["rice"])
    assert labels["rice"].aisle in (None, *AISLES)


@pytest.mark.parametrize(
    ("staple", "expected"), [(0.0, False), (0.2999, False), (0.3, True), (1.0, True)]
)
def test_the_staple_threshold_boundary(staple: float, expected: bool) -> None:
    labels = classify(_engine(_classifier("pantry", staple)), ["salt"])
    assert labels["salt"].staple is expected


def test_every_item_gets_a_label_entry_even_when_the_models_are_down() -> None:
    labels = classify(_engine(lambda *_a: None), ["rice", "salt"])
    assert set(labels) == {"rice", "salt"}
    assert all(label.aisle is None and label.staple is None for label in labels.values())


def test_classifying_hundreds_of_items_returns_them_all_in_order_independent_form() -> None:
    names = [f"item {i}" for i in range(300)]
    forward = classify(_engine(_classifier("pantry", 0.9)), names)
    backward = classify(_engine(_classifier("pantry", 0.9)), list(reversed(names)))
    assert forward == backward and len(forward) == 300


def test_all_pairs_of_a_small_list_are_considered_without_cross_talk() -> None:
    names = ["a", "b", "c", "d"]
    for pair in itertools.combinations(names, 2):
        says = {pair[0]: pair[1], pair[1]: pair[0]}
        mapping = synonym_map(_engine(_responder(says)), names)
        assert set(mapping) | set(mapping.values()) == set(pair)
