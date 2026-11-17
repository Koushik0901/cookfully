from __future__ import annotations

from decimal import Decimal

from cookfully.application.suggestions import _penalty
from cookfully.application.taste_scores import score_from, taste_ask
from cookfully.domain.decisions import Answers, ModelAnswers

D = Decimal


def _answers(**checks: str) -> Answers:
    return Answers({"m1": ModelAnswers({}, {key: D(value) for key, value in checks.items()}, {})})


def test_score_weights_taste_twice_satisfying_meal() -> None:
    assert score_from(_answers(satisfying="0.9", like="0.3")) == (D(2) * D("0.3") + D("0.9")) / 3
    assert score_from(_answers(satisfying="0.6")) == D("0.6")
    assert score_from(Answers()) is None


def test_the_taste_question_is_asked_only_with_favourites() -> None:
    assert set(taste_ask("Soup", ["1 onion"], []).questions) == {"satisfying"}
    with_likes = taste_ask("Soup", ["1 onion"], ["Ramen", "Pho"])
    assert set(with_likes.questions) == {"satisfying", "like"}
    assert with_likes.state["liked_recipes"] == "Ramen\nPho"


def test_penalty_maps_scores_and_treats_unknown_as_neutral_only_when_others_are_scored() -> None:
    assert _penalty(D(1), any_scores=True) == 0
    assert _penalty(D(0), any_scores=True) == 1000
    assert _penalty(D("0.75"), any_scores=True) == 250
    assert _penalty(None, any_scores=True) == 500
    assert _penalty(None, any_scores=False) == 0
    assert _penalty(D(2), any_scores=True) == 0
