from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

from cookfully.application.decision_assist import (
    AssistLine,
    DecisionAssist,
    nutrients_per_100g,
)
from cookfully.domain.decision_assist import (
    AssistAction,
    AssistOption,
    evaluate,
    normalize_probabilities,
)
from cookfully.domain.ingredient_nutrition.matching import FoodCandidate
from cookfully.infrastructure.decision_client import OpenRouterDecisionClient

D = Decimal


def _nutrients(**overrides: str) -> dict[str, D | None]:
    base = {
        "calories_kcal": D(0),
        "protein_g": D(0),
        "fat_g": D(0),
        "carbohydrate_g": D(0),
        "sodium_mg": D(0),
        "vitamin_c_mg": D(0),
    }
    return {**base, **{key: D(value) for key, value in overrides.items()}}


OLIVE_A = AssistOption("c1", _nutrients(calories_kcal="884", fat_g="100"))
OLIVE_B = AssistOption("c2", _nutrients(calories_kcal="880", fat_g="99"))
BUTTER = AssistOption("c3", _nutrients(calories_kcal="717", fat_g="81", sodium_mg="643"))
LIME = AssistOption("c4", _nutrients(calories_kcal="30", vitamin_c_mg="29"))


def test_tie_between_near_identical_foods_auto_resolves() -> None:
    verdict = evaluate([OLIVE_A, OLIVE_B], {"c1": 0.5, "c2": 0.5}, grams=D(14))
    assert verdict.action is AssistAction.AUTO_RESOLVE
    assert verdict.top_key == "c1"


def test_uncertain_butter_vs_lime_needs_review_for_a_large_quantity() -> None:
    verdict = evaluate([BUTTER, LIME], {"c3": 0.6, "c4": 0.4}, grams=D(113))
    assert verdict.action is AssistAction.REVIEW
    assert verdict.reason == "expected_error_above_tolerance"


def test_small_quantity_makes_the_same_uncertainty_harmless() -> None:
    verdict = evaluate([BUTTER, LIME], {"c3": 0.6, "c4": 0.4}, grams=D("0.5"))
    assert verdict.action is AssistAction.AUTO_RESOLVE


def test_sodium_alone_can_force_review_when_calories_would_pass() -> None:
    salty = AssistOption("c1", _nutrients(calories_kcal="0", sodium_mg="38000"))
    plain = AssistOption("c2", _nutrients(calories_kcal="0"))
    verdict = evaluate([salty, plain], {"c1": 0.7, "c2": 0.3}, grams=D(30))
    assert verdict.action is AssistAction.REVIEW
    assert verdict.expected_error_dv["calories_kcal"] == 0
    assert verdict.expected_error_dv["sodium_mg"] > D("0.02")


def test_none_winner_is_never_applied() -> None:
    verdict = evaluate([OLIVE_A], {"c1": 0.1, "none": 0.9}, grams=D(5))
    assert verdict.action is AssistAction.REVIEW
    assert verdict.reason == "model_rejected_options"


def test_none_probability_counts_as_a_food_with_no_nutrients() -> None:
    confident = evaluate([BUTTER], {"c3": 0.99, "none": 0.01}, grams=D(113))
    unsure = evaluate([BUTTER], {"c3": 0.6, "none": 0.4}, grams=D(113))
    assert confident.action is AssistAction.AUTO_RESOLVE
    assert unsure.action is AssistAction.REVIEW


def test_unknown_quantity_fails_closed() -> None:
    verdict = evaluate([OLIVE_A], {"c1": 1.0}, grams=None)
    assert verdict.action is AssistAction.REVIEW
    assert verdict.reason == "quantity_unknown"


def test_missing_nutrient_on_top_option_fails_closed() -> None:
    incomplete = AssistOption("c1", {"calories_kcal": D(10)})
    verdict = evaluate([incomplete], {"c1": 1.0}, grams=D(10))
    assert verdict.action is AssistAction.REVIEW
    assert verdict.reason == "nutrient_missing"


def test_missing_nutrient_on_a_competing_option_fails_closed() -> None:
    incomplete = AssistOption("c2", {"calories_kcal": D(10)})
    verdict = evaluate([OLIVE_A, incomplete], {"c1": 0.9, "c2": 0.1}, grams=D(10))
    assert verdict.reason == "nutrient_missing"


@pytest.mark.parametrize(
    "raw",
    [{}, {"zzz": 1.0}, {"c1": -0.1}, {"c1": 1.5}, {"c1": float("nan")}, {"c1": "bad"}, {"c1": 0}],
)
def test_unusable_probabilities_fail_closed(raw: dict[str, Any]) -> None:
    verdict = evaluate([OLIVE_A], raw, grams=D(5))
    assert verdict.action is AssistAction.REVIEW
    assert verdict.reason == "unusable_probabilities"


def test_probabilities_are_renormalized_and_unknown_keys_dropped() -> None:
    result = normalize_probabilities({"c1": 0.3, "c2": 0.1, "ghost": 0.9}, ["c1", "c2"])
    assert result == {"c1": D("0.75"), "c2": D("0.25")}


def test_equal_probability_prefers_a_real_food_over_none() -> None:
    verdict = evaluate([OLIVE_A], {"c1": 0.5, "none": 0.5}, grams=D(1))
    assert verdict.top_key == "c1"


# --- service ------------------------------------------------------------------------------------


def _food(description: str, **codes: str) -> Any:
    nutrients = [
        SimpleNamespace(nutrient_code=code, amount=D(value), canonical_key=None)
        for code, value in codes.items()
    ]
    return SimpleNamespace(
        id=uuid4(),
        description=description,
        food_category="Fats and Oils",
        basis_grams=D(100),
        nutrients=nutrients,
    )


def _candidate(food: Any) -> FoodCandidate:
    return FoodCandidate(food, D("0.7"))


class _Chooser:
    model = "test/model"

    def __init__(self, answer: dict[str, float] | None) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def choose(self, *, state: Any, instructions: str, criteria: Any) -> dict[str, float] | None:
        self.calls.append({"state": dict(state), "criteria": dict(criteria)})
        return self.answer


LINE = AssistLine("1 tbsp olive oil", "olive oil", "Salad", D(14))


def test_nutrients_per_100g_scales_to_basis_and_applies_atwater_and_zero_defaults() -> None:
    food = _food("Oil", **{"203": "2", "204": "10", "205": "20"})
    food.basis_grams = D(50)
    values = nutrients_per_100g(food)
    assert values["protein_g"] == D(4)
    assert values["calories_kcal"] == D(4) * 4 + D(4) * 40 + D(9) * 20
    assert values["sodium_mg"] == 0


def test_nutrients_per_100g_reads_micronutrients_by_fdc_id_and_canonical_key() -> None:
    food = _food("Salt", **{"1093": "38000", "1008": "0"})
    food.nutrients.append(
        SimpleNamespace(nutrient_code="x", amount=D(9), canonical_key="vitamin_c_mg")
    )
    values = nutrients_per_100g(food)
    assert values["sodium_mg"] == 38000
    assert values["vitamin_c_mg"] == 9


def test_service_applies_the_models_pick_and_records_provenance() -> None:
    a = _food("Oil, olive", **{"208": "884", "204": "100"})
    b = _food("Oil, olive, extra light", **{"208": "880", "204": "99"})
    chooser = _Chooser({"c2": 0.7, "c1": 0.3})
    outcome = DecisionAssist(chooser, tolerance_dv=D("0.02")).resolve(
        LINE, [_candidate(a), _candidate(b)]
    )
    assert outcome is not None
    assert outcome.candidate.food is b
    evidence = outcome.evidence
    assert evidence["model"] == "test/model"
    assert evidence["toleranceDv"] == "0.02"
    assert cast(list[dict[str, str]], evidence["probabilities"])[0]["foodReferenceId"] == str(b.id)
    sent = chooser.calls[0]
    assert sent["state"] == {
        "recipe": "Salad",
        "ingredient_line": "1 tbsp olive oil",
        "parsed_food_name": "olive oil",
    }
    assert sent["criteria"]["c1"] == "Oil, olive [Fats and Oils]"
    assert "none" in sent["criteria"]


def test_service_keeps_deterministic_result_when_uncertain_or_unavailable() -> None:
    butter = _food("Butter", **{"208": "717", "204": "81", "307": "643"})
    lime = _food("Lime", **{"208": "30", "401": "29"})
    big = AssistLine("1 cup butter", "butter", "Cake", D(227))
    unsure = DecisionAssist(_Chooser({"c1": 0.6, "c2": 0.4}), tolerance_dv=D("0.02"))
    assert unsure.resolve(big, [_candidate(butter), _candidate(lime)]) is None
    down = DecisionAssist(_Chooser(None), tolerance_dv=D("0.02"))
    assert down.resolve(big, [_candidate(butter)]) is None
    assert down.resolve(big, []) is None


def test_service_limits_options_sent_to_the_model() -> None:
    foods = [_food(f"Food {i}", **{"208": "1"}) for i in range(20)]
    chooser = _Chooser({"c1": 1.0})
    DecisionAssist(chooser, tolerance_dv=D("0.02"), max_options=5).resolve(
        LINE, [_candidate(food) for food in foods]
    )
    assert set(chooser.calls[0]["criteria"]) == {"c1", "c2", "c3", "c4", "c5", "none"}


# --- client -------------------------------------------------------------------------------------


def _client(handler: Any) -> OpenRouterDecisionClient:
    return OpenRouterDecisionClient(
        api_key="secret",
        model="typesafe/jev-1.14",
        url="https://example.test/decisions",
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_client_sends_bearer_key_and_parses_probabilities() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "answers": {"match": {"type": "choice", "probabilities": {"c1": 0.9, "none": 0.1}}}
            },
        )

    result = _client(handler).choose(
        state={"ingredient_line": "x"}, instructions="pick", criteria={"c1": "A", "none": "N"}
    )
    assert result == {"c1": 0.9, "none": 0.1}
    assert seen["auth"] == "Bearer secret"
    assert seen["body"]["model"] == "typesafe/jev-1.14"
    assert seen["body"]["questions"]["match"]["type"] == "choice"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={}),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"answers": {}}),
        httpx.Response(200, json={"answers": {"match": {"type": "noul", "noul": 0.5}}}),
        httpx.Response(
            200, json={"answers": {"match": {"type": "choice", "probabilities": {"c1": "x"}}}}
        ),
    ],
)
def test_client_returns_none_for_any_failure(response: httpx.Response) -> None:
    assert (
        _client(lambda _request: response).choose(state={}, instructions="i", criteria={}) is None
    )


def test_client_returns_none_on_network_error() -> None:
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert _client(boom).choose(state={}, instructions="i", criteria={}) is None


def test_client_falls_back_to_single_choice_confidence() -> None:
    payload = {"answers": {"match": {"type": "choice", "choice": "c2", "confidence": 0.8}}}
    result = _client(lambda _r: httpx.Response(200, json=payload)).choose(
        state={}, instructions="i", criteria={}
    )
    assert result == {"c2": 0.8}


# --- pipeline hook ------------------------------------------------------------------------------


def _constant(value: Any) -> Any:
    return lambda _session: value


def _pipeline() -> Any:
    from cookfully.jobs.recipe_pipeline import RecipePipeline

    return object.__new__(RecipePipeline)


def _ingredient(text: str, name: str, quantity: str, unit: str) -> Any:
    return SimpleNamespace(
        original_text=text,
        food_name=name,
        quantity_min=D(quantity),
        quantity_max=D(quantity),
        unit_code=unit,
        optional=False,
    )


def test_pipeline_replaces_an_ambiguous_decision_when_the_assist_is_confident() -> None:
    from cookfully.domain.ingredient_nutrition.matching import MatchDecision

    a = _candidate(_food("Oil, olive", **{"208": "884", "204": "100"}))
    b = _candidate(_food("Oil, olive, light", **{"208": "880", "204": "99"}))
    assist = DecisionAssist(_Chooser({"c2": 0.8, "c1": 0.2}), tolerance_dv=D("0.02"))
    decision, evidence = _pipeline()._assisted(
        assist,
        MatchDecision("ambiguous", "ranked", None, (a, b)),
        _ingredient("1 tbsp olive oil", "olive oil", "14", "gram"),
        "Salad",
    )
    assert decision.status == "matched"
    assert decision.method == "decision_assist"
    assert decision.candidate is b
    assert decision.alternatives == (a,)
    assert evidence is not None
    assert evidence["kind"] == "decision_assist"


def test_pipeline_keeps_the_deterministic_decision_when_the_assist_declines() -> None:
    from cookfully.domain.ingredient_nutrition.matching import MatchDecision

    a = _candidate(_food("Butter", **{"208": "717", "204": "81", "307": "643"}))
    b = _candidate(_food("Lime", **{"208": "30", "401": "29"}))
    original = MatchDecision("matched", "ranked", a, (b,))
    assist = DecisionAssist(_Chooser({"c1": 0.6, "c2": 0.4}), tolerance_dv=D("0.02"))
    decision, evidence = _pipeline()._assisted(
        assist, original, _ingredient("1 cup butter", "butter", "227", "gram"), "Cake"
    )
    assert decision is original
    assert evidence is None


def test_pipeline_does_not_call_the_model_without_candidates() -> None:
    from cookfully.domain.ingredient_nutrition.matching import MatchDecision

    chooser = _Chooser({"c1": 1.0})
    original = MatchDecision("unmatched", "ranked", None, ())
    decision, evidence = _pipeline()._assisted(
        DecisionAssist(chooser, tolerance_dv=D("0.02")),
        original,
        _ingredient("x", "x", "1", "gram"),
        "R",
    )
    assert decision is original and evidence is None and chooser.calls == []


def test_pipeline_builds_the_assist_only_with_a_usable_key_and_the_switch_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cookfully.application.openrouter_settings import OpenRouterConfig

    def config(key: str | None, enabled: bool) -> OpenRouterConfig:
        return OpenRouterConfig(key, "", enabled, "typesafe/jev-1.14", D("0.03"))

    pipeline = _pipeline()
    for key, enabled, expected in [(None, True, False), ("k", False, False), ("k", True, True)]:
        monkeypatch.setattr(
            "cookfully.jobs.recipe_pipeline.load_openrouter_config",
            _constant(config(key, enabled)),
        )
        assist = pipeline._decision_assist(None)
        assert (assist is not None) is expected
        if assist is not None:
            assert assist._tolerance == D("0.03")
