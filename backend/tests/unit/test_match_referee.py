from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.match_referee import (
    MatchReferee,
    RefereeLine,
    nutrients_per_100g,
)
from cookfully.domain.decision_assist import (
    AssistAction,
    AssistOption,
    evaluate,
    normalize_probabilities,
)
from cookfully.domain.decisions import Answers, Purpose
from cookfully.domain.ingredient_nutrition.matching import FoodCandidate, MatchDecision
from cookfully.domain.match_referee import (
    RefereeAction,
    RefereeVerdict,
    check_state,
    judge,
    switch_impact_dv,
)
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore

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


# --- referee rule ------------------------------------------------------------------------------

TOL = D("0.02")


def test_uncertain_line_is_upgraded_when_the_primary_passes_and_the_panel_agrees() -> None:
    panel = [{"c1": D("0.6"), "c2": D("0.4")}, {"c1": D("0.5"), "c2": D("0.3"), "none": D("0.2")}]
    verdict = judge([OLIVE_A, OLIVE_B], panel, current=None, grams=D(14), tolerance_dv=TOL)
    assert verdict.action is RefereeAction.UPGRADE
    assert verdict.pick == "c1"


def test_uncertain_line_stays_in_review_when_another_model_disagrees() -> None:
    panel = [{"c1": D("0.6"), "c2": D("0.4")}, {"c1": D("0.2"), "c2": D("0.8")}]
    verdict = judge([OLIVE_A, OLIVE_B], panel, current=None, grams=D(14), tolerance_dv=TOL)
    assert verdict.action is RefereeAction.KEEP
    assert verdict.reason == "panel_split"


def test_uncertain_line_uses_the_primary_distribution_not_the_average() -> None:
    # The primary is sure; the second model agrees but is flatter. Averaging would push the
    # expected error over tolerance for a large amount of butter; the primary alone does not.
    panel = [{"c3": D("0.99"), "c4": D("0.01")}, {"c3": D("0.55"), "c4": D("0.45")}]
    verdict = judge([BUTTER, LIME], panel, current=None, grams=D(20), tolerance_dv=TOL)
    assert verdict.action is RefereeAction.UPGRADE


def test_confident_match_is_downgraded_when_the_panel_agrees_on_a_food_that_matters() -> None:
    panel = [{"c3": D("0.1"), "c4": D("0.9")}, {"c3": D("0.2"), "c4": D("0.8")}]
    verdict = judge([BUTTER, LIME], panel, current="c3", grams=D(100), tolerance_dv=TOL)
    assert verdict.action is RefereeAction.DOWNGRADE
    assert verdict.reason == "disagreement_matters"
    assert verdict.pick == "c4"
    assert verdict.impact_dv is not None and verdict.impact_dv > TOL


def test_harmless_disagreement_is_confirmed_and_recorded() -> None:
    panel = [{"c1": D("0.1"), "c2": D("0.9")}, {"c1": D("0.3"), "c2": D("0.7")}]
    verdict = judge([OLIVE_A, OLIVE_B], panel, current="c1", grams=D(14), tolerance_dv=TOL)
    assert verdict.action is RefereeAction.CONFIRM
    assert verdict.reason == "disagreement_harmless"


def test_split_or_unsure_panel_confirms_the_match() -> None:
    split = [{"c3": D("0.1"), "c4": D("0.9")}, {"c3": D("0.9"), "c4": D("0.1")}]
    unsure = [{"c3": D("0.45"), "c4": D("0.55")}, {"c3": D("0.4"), "c4": D("0.6")}]
    unsure_mean = judge([BUTTER, LIME], unsure, current="c3", grams=D(100), tolerance_dv=TOL)
    split_v = judge([BUTTER, LIME], split, current="c3", grams=D(100), tolerance_dv=TOL)
    assert split_v.action is RefereeAction.CONFIRM and split_v.reason == "panel_split"
    assert unsure_mean.action is RefereeAction.DOWNGRADE  # mean 0.575 >= 0.5
    stricter = judge(
        [BUTTER, LIME],
        unsure,
        current="c3",
        grams=D(100),
        tolerance_dv=TOL,
        min_downgrade_probability=D("0.7"),
    )
    assert stricter.action is RefereeAction.CONFIRM and stricter.reason == "disagreement_unsure"


def test_panel_agreeing_on_none_downgrades_a_match() -> None:
    panel = [{"c3": D("0.1"), "none": D("0.9")}]
    verdict = judge([BUTTER], panel, current="c3", grams=D(5), tolerance_dv=TOL)
    assert verdict.action is RefereeAction.DOWNGRADE
    assert verdict.reason == "panel_rejects_match"


def test_unknown_quantity_downgrades_a_confident_disagreement() -> None:
    panel = [{"c3": D("0.1"), "c4": D("0.9")}]
    verdict = judge([BUTTER, LIME], panel, current="c3", grams=None, tolerance_dv=TOL)
    assert verdict.action is RefereeAction.DOWNGRADE
    assert verdict.reason == "disagreement_impact_unknown"


def test_no_usable_answer_keeps_the_deterministic_result() -> None:
    assert judge([BUTTER], [], current="c3", grams=D(5), tolerance_dv=TOL).action is (
        RefereeAction.CONFIRM
    )
    assert judge([BUTTER], [{"x": D(1)}], current=None, grams=D(5), tolerance_dv=TOL).action is (
        RefereeAction.KEEP
    )


def test_switch_impact_is_the_largest_nutrient_change_as_share_of_daily_value() -> None:
    impact = switch_impact_dv([BUTTER, LIME], "c3", "c4", D(100))
    assert impact == D(81) / D(78)  # fat moves the most
    assert switch_impact_dv([BUTTER, LIME], "c3", "c4", None) is None


# --- prep state ---------------------------------------------------------------------------------

DRY_RICE = AssistOption("c1", _nutrients(calories_kcal="365", carbohydrate_g="80"))
COOKED_RICE = AssistOption("c2", _nutrients(calories_kcal="130", carbohydrate_g="28"))
RICE_STATES = {"c1": "raw", "c2": "cooked"}
COOKED = {"cooked": D("0.9"), "raw": D("0.05"), "unspecified": D("0.05")}
CONFIRMED = RefereeVerdict(RefereeAction.CONFIRM, "panel_agrees", "c1", D("0.9"), None)


def _state(verdict: RefereeVerdict, line_state: Any, **kwargs: Any) -> RefereeVerdict:
    defaults: dict[str, Any] = {
        "current": "c1",
        "grams": D(180),
        "tolerance_dv": TOL,
        "agreed": True,
    }
    return check_state(
        verdict, [DRY_RICE, COOKED_RICE], RICE_STATES, line_state, **(defaults | kwargs)
    )


def test_cooked_line_matched_to_dry_food_goes_to_review_with_the_cooked_food_first() -> None:
    verdict = _state(CONFIRMED, COOKED)
    assert verdict.action is RefereeAction.DOWNGRADE
    assert verdict.reason == "state_mismatch"
    assert verdict.pick == "c2"


def test_state_check_needs_a_confident_agreed_state() -> None:
    unsure = {"cooked": D("0.6"), "raw": D("0.4")}
    assert _state(CONFIRMED, unsure) is CONFIRMED
    assert _state(CONFIRMED, COOKED, agreed=False) is CONFIRMED
    assert _state(CONFIRMED, None) is CONFIRMED
    assert _state(CONFIRMED, {"unspecified": D("0.95")}) is CONFIRMED


def test_matching_state_or_harmless_switch_is_left_alone() -> None:
    assert _state(CONFIRMED, COOKED, current="c2") is CONFIRMED
    assert _state(CONFIRMED, COOKED, grams=D(1)) is CONFIRMED


def test_contradicting_upgrade_is_held_back() -> None:
    upgrade = RefereeVerdict(
        RefereeAction.UPGRADE, "expected_error_within_tolerance", "c1", D(1), None
    )
    verdict = _state(upgrade, COOKED, current=None)
    assert verdict.action is RefereeAction.KEEP
    assert verdict.reason == "state_mismatch"
    assert verdict.pick == "c2"


def test_contradiction_without_a_fitting_food_still_goes_to_review() -> None:
    verdict = check_state(
        CONFIRMED,
        [DRY_RICE],
        {"c1": "raw"},
        COOKED,
        current="c1",
        grams=D(180),
        tolerance_dv=TOL,
        agreed=True,
    )
    assert verdict.action is RefereeAction.DOWNGRADE
    assert verdict.reason == "state_mismatch_no_fitting_food"


# --- referee service ----------------------------------------------------------------------------


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


PANEL = ("m1", "m2")


class _Panel:
    """Answers the match question through the real engine with a scripted transport."""

    def __init__(
        self,
        answers: dict[str, dict[str, float] | None],
        line_state: dict[str, float] | None = None,
    ) -> None:
        self.answers = answers
        self.line_state = line_state
        self.calls: list[dict[str, Any]] = []
        self._engine = Decisions(
            DecisionsConfig(
                api_key="k",
                features={Purpose.MATCH_REFEREE: FeatureConfig(models=tuple(answers))},
            ),
            ScriptedDecisionTransport(self._respond),
            InMemoryDecisionStore(),
        )

    def _respond(self, model: str, state: Any, questions: Any) -> object:
        answer = self.answers[model]
        if "state" in questions:
            if answer is None:
                return None
            line_state = self.line_state or {"unspecified": 1.0}
            return {"state": {"type": "choice", "probabilities": line_state}}
        self.calls.append(
            {"model": model, "state": dict(state), "criteria": dict(questions["match"]["criteria"])}
        )
        if answer is None:
            return None
        return {"match": {"type": "choice", "probabilities": answer}}

    def ask(self, asks: Any) -> list[Answers]:
        return self._engine.ask(asks)


def _referee(
    answers: dict[str, dict[str, float] | None], **kwargs: Any
) -> tuple[MatchReferee, _Panel]:
    panel = _Panel(answers)
    return MatchReferee(panel, panel=tuple(answers), tolerance_dv=TOL, **kwargs), panel


OIL = RefereeLine("1 tbsp olive oil", "olive oil", "Salad", D(14))
BUTTER_LINE = RefereeLine("1 cup butter", "butter", "Cake", D(227))
OLIVE = _food("Oil, olive", **{"208": "884", "204": "100"})
LIGHT = _food("Oil, olive, extra light", **{"208": "880", "204": "99"})
BUTTER_FOOD = _food("Butter", **{"208": "717", "204": "81", "307": "643"})
LIME_FOOD = _food("Lime", **{"208": "30", "401": "29"})


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


def test_ambiguous_line_is_resolved_with_provenance() -> None:
    referee, panel = _referee({"m1": {"c2": 0.7, "c1": 0.3}, "m2": {"c2": 0.6, "c1": 0.4}})
    a, b = _candidate(OLIVE), _candidate(LIGHT)
    judgement = referee.judge(OIL, MatchDecision("ambiguous", "ranked", None, (a, b)))
    assert judgement.decision.status == "matched"
    assert judgement.decision.method == "decision_referee"
    assert judgement.decision.candidate is b
    assert judgement.decision.alternatives == (a,)
    evidence = judgement.evidence
    assert evidence is not None
    assert evidence["kind"] == "match_referee"
    assert evidence["action"] == "upgrade"
    assert evidence["models"] == ["m1", "m2"]
    assert cast(dict[str, str], evidence["pick"])["foodReferenceId"] == str(LIGHT.id)
    sent = panel.calls[0]
    assert sent["state"] == {
        "recipe": "Salad",
        "ingredient_line": "1 tbsp olive oil",
        "parsed_food_name": "olive oil",
    }
    assert sent["criteria"]["c1"] == "Oil, olive [Fats and Oils]"
    assert "none" in sent["criteria"]


def test_confident_wrong_match_goes_to_review_with_the_panels_pick_first() -> None:
    referee, _ = _referee({"m1": {"c1": 0.05, "c2": 0.95}, "m2": {"c1": 0.1, "c2": 0.9}})
    butter, lime = _candidate(BUTTER_FOOD), _candidate(LIME_FOOD)
    judgement = referee.judge(
        RefereeLine("juice of 1 lime", "lime", "Tacos", D(100)),
        MatchDecision("matched", "ranked", butter, (lime,)),
    )
    assert judgement.decision.status == "ambiguous"
    assert judgement.decision.candidate is None
    assert judgement.decision.alternatives == (lime, butter)
    assert judgement.evidence is not None and judgement.evidence["action"] == "downgrade"


def test_confirmed_match_is_unchanged_but_evidence_is_recorded() -> None:
    referee, _ = _referee({"m1": {"c1": 0.9, "c2": 0.1}, "m2": {"c1": 0.8, "c2": 0.2}})
    original = MatchDecision("matched", "ranked", _candidate(OLIVE), (_candidate(LIGHT),))
    judgement = referee.judge(OIL, original)
    assert judgement.decision is original
    assert judgement.evidence is not None and judgement.evidence["action"] == "confirm"


def test_failures_memory_matches_and_empty_candidates_keep_the_deterministic_result() -> None:
    down, _ = _referee({"m1": None, "m2": None})
    original = MatchDecision("matched", "ranked", _candidate(BUTTER_FOOD), (_candidate(LIME_FOOD),))
    assert down.judge(BUTTER_LINE, original).decision is original
    assert down.judge(BUTTER_LINE, original).evidence is None

    referee, panel = _referee({"m1": {"c1": 1.0}})
    remembered = MatchDecision("matched", "memory", _candidate(BUTTER_FOOD), ())
    assert referee.judge(BUTTER_LINE, remembered).decision is remembered
    empty = MatchDecision("unmatched", "ranked", None, ())
    assert referee.judge(BUTTER_LINE, empty).decision is empty
    assert panel.calls == []


def test_uncertain_large_amount_stays_in_review() -> None:
    referee, _ = _referee({"m1": {"c1": 0.6, "c2": 0.4}})
    original = MatchDecision(
        "ambiguous", "ranked", None, (_candidate(BUTTER_FOOD), _candidate(LIME_FOOD))
    )
    judgement = referee.judge(BUTTER_LINE, original)
    assert judgement.decision is original
    assert judgement.evidence is not None and judgement.evidence["action"] == "keep"


def test_cooked_line_matched_to_dry_rice_is_sent_to_review_by_the_service() -> None:
    dry = _food("Rice, white, long-grain, regular, raw, enriched", **{"208": "365", "205": "80"})
    cooked = _food("Rice, white, long-grain, regular, cooked", **{"208": "130", "205": "28"})
    panel = _Panel({"m1": {"c1": 0.9, "c2": 0.1}}, line_state={"cooked": 0.95, "raw": 0.05})
    referee = MatchReferee(panel, panel=("m1",), tolerance_dv=TOL)
    judgement = referee.judge(
        RefereeLine("2 cups leftover rice", "rice", "Fried rice", D(316)),
        MatchDecision("matched", "ranked", _candidate(dry), (_candidate(cooked),)),
    )
    assert judgement.decision.status == "ambiguous"
    assert judgement.decision.alternatives[0].food is cooked
    evidence = judgement.evidence
    assert evidence is not None
    assert evidence["reason"] == "state_mismatch"
    line_state = cast(dict[str, str], evidence["lineState"])
    assert line_state["state"] == "cooked"
    assert D(line_state["probability"]) == D("0.95")


def test_options_sent_to_the_panel_are_limited() -> None:
    foods = [_food(f"Food {i}", **{"208": "1"}) for i in range(20)]
    referee, panel = _referee({"m1": {"c1": 1.0}}, max_options=5)
    referee.judge(OIL, MatchDecision("ambiguous", "ranked", None, tuple(map(_candidate, foods))))
    assert set(panel.calls[0]["criteria"]) == {"c1", "c2", "c3", "c4", "c5", "none"}


# --- pipeline hook ------------------------------------------------------------------------------


def _constant(value: Any) -> Any:
    return lambda _session: value


def _pipeline() -> Any:
    from cookfully.jobs.recipe_pipeline import RecipePipeline

    pipeline = object.__new__(RecipePipeline)
    pipeline._session_factory = None
    return pipeline


def _ingredient(text: str, name: str, quantity: str, unit: str) -> Any:
    return SimpleNamespace(
        original_text=text,
        food_name=name,
        quantity_min=D(quantity),
        quantity_max=D(quantity),
        unit_code=unit,
        optional=False,
    )


def test_pipeline_passes_grams_from_the_line_to_the_referee() -> None:
    referee, _ = _referee({"m1": {"c2": 0.8, "c1": 0.2}})
    a, b = _candidate(OLIVE), _candidate(LIGHT)
    judgement = _pipeline()._refereed(
        referee,
        MatchDecision("ambiguous", "ranked", None, (a, b)),
        _ingredient("14 g olive oil", "olive oil", "14", "gram"),
        "Salad",
    )
    assert judgement.decision.candidate is b


def test_pipeline_builds_the_referee_only_with_a_usable_key_and_the_switch_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cookfully.application.decisions import DEFAULT_FEATURES
    from cookfully.application.openrouter_settings import OpenRouterConfig

    def config(key: str | None, enabled: bool) -> OpenRouterConfig:
        features = dict(DEFAULT_FEATURES)
        features[Purpose.MATCH_REFEREE] = FeatureConfig(enabled, PANEL)
        return OpenRouterConfig(key, "", D("0.03"), features)

    pipeline = _pipeline()
    for key, enabled, expected in [(None, True, False), ("k", False, False), ("k", True, True)]:
        monkeypatch.setattr(
            "cookfully.jobs.recipe_pipeline.load_openrouter_config",
            _constant(config(key, enabled)),
        )
        referee = pipeline._match_referee(None)
        assert (referee is not None) is expected
        if referee is not None:
            assert referee._tolerance == D("0.03")
            assert referee._panel == PANEL
