from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from cookfully.application.food_labels import labels_from
from cookfully.domain.decisions import Answers, ModelAnswers
from cookfully.domain.food_labels import FoodLabels, label_penalty

D = Decimal
RAW = FoodLabels("raw", D("0.95"), "generic", D("0.9"), D("0.05"))
COOKED = FoodLabels("cooked", D("0.95"), "generic", D("0.9"), D("0.05"))


def test_confident_state_contradictions_are_penalised() -> None:
    assert label_penalty("cooked rice", RAW) == D("0.08")
    assert label_penalty("raw spinach", COOKED) == D("0.08")
    assert label_penalty("rice", COOKED) == D("0.04")  # unspecified lines prefer as-bought
    assert label_penalty("rice", RAW) == 0
    assert label_penalty("cooked rice", COOKED) == 0


def test_flavoured_and_processed_entries_cost_extra_unless_the_line_says_so() -> None:
    flavored = FoodLabels("raw", D("0.9"), "processed", D("0.9"), D("0.9"))
    assert label_penalty("yogurt", flavored) == D("0.08")
    assert label_penalty("vanilla yogurt", flavored) == D("0.03")
    assert label_penalty("pasta sauce", flavored) == D("0.05")


def test_unsure_or_missing_labels_change_nothing() -> None:
    assert label_penalty("cooked rice", None) == 0
    assert label_penalty("cooked rice", FoodLabels("raw", D("0.6"))) == 0


def test_labels_round_trip_from_answers() -> None:
    answers = Answers(
        {
            "m1": ModelAnswers(
                {"state": {"raw": D("0.9"), "cooked": D("0.1")}, "kind": {"generic": D(1)}},
                {"flavored": D("0.1"), "contains_gluten": D("0.02")},
                {},
            )
        }
    )
    payload = labels_from(answers)
    assert payload is not None
    labels = FoodLabels.from_json(payload)
    assert (labels.state, labels.state_probability, labels.kind) == ("raw", D("0.9"), "generic")
    assert {k: D(v) for k, v in payload["allergens"].items()} == {"gluten": D("0.02")}
    assert labels_from(Answers()) is None


def test_matcher_demotes_candidates_their_labels_contradict() -> None:
    from cookfully.domain.ingredient_nutrition.matching import FoodMatcher

    def food(description: str) -> Any:
        return SimpleNamespace(
            id=uuid4(),
            description=description,
            normalized_name=description.lower(),
            external_id=description,
            food_category=None,
            basis_grams=D(100),
            nutrients=[],
        )

    raw, cooked = food("Rice, white, raw"), food("Rice, white, cooked")

    class Repo:
        def search_foods_for_matching(self, _query: str, *, limit: int) -> list[Any]:
            del limit
            return [raw, cooked]

    labels = {raw.id: RAW, cooked.id: COOKED}
    plain = FoodMatcher(Repo(), candidate_pool_limit=10)  # type: ignore[arg-type]
    with_labels = FoodMatcher(
        Repo(),  # type: ignore[arg-type]
        candidate_pool_limit=10,
        labels_for=lambda batch: {f.id: labels[f.id] for f in batch},
    )
    # "rice" names no state: a confidently cooked entry loses a little to the as-bought one.
    plain_scores = {c.food.id: c.score for c in plain.candidates("white rice")}
    labelled = {c.food.id: c for c in with_labels.candidates("white rice")}
    assert labelled[cooked.id].score == max(D(0), plain_scores[cooked.id] - D("0.04"))
    assert "label_mismatch" in labelled[cooked.id].reasons
    assert labelled[raw.id].score == plain_scores[raw.id]
