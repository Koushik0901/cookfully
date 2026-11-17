"""The match referee: a second opinion from a panel of decision models on every food match.

The deterministic matcher always runs first. The referee then asks the owner's model panel to pick
among the matcher's candidates and applies ``domain.match_referee.judge``: an ambiguous line can be
resolved when the remaining doubt cannot move the nutrition, and a confident deterministic match is
sent to review when the panel agrees on a different food that would change the nutrition. Everything
else, including every failure, keeps the deterministic result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from cookfully.domain.decision_assist import NONE_KEY, TRACKED_DAILY_VALUES, AssistOption
from cookfully.domain.decisions import Answers, Ask, Choice, Purpose
from cookfully.domain.ingredient_nutrition.matching import FoodCandidate, MatchDecision
from cookfully.domain.match_referee import RefereeAction, RefereeVerdict, judge
from cookfully.domain.nutrition import CORE_NUTRIENT_CODES, USDA_MICRONUTRIENT_MANIFEST
from cookfully.infrastructure.models.reference_foods import FoodReference

MATCH_INSTRUCTIONS = (
    "Which USDA FoodData Central entry best represents this recipe ingredient for nutrition "
    "lookup? Match the food and the state implied by the line (raw for fresh produce and meat, "
    "dry for grains and pasta unless the line says cooked, drained for canned foods). Prefer "
    "plain generic entries over flavored, processed, branded or different-part variants. "
    "Answer none if no entry is an acceptable match or the line is not a food ingredient."
)
NONE_CRITERION = (
    "None of the listed entries is an acceptable match, or this line is not a food ingredient."
)
PROVENANCE_VERSION = "match-referee-v1"
METHOD = "decision_referee"
DEFAULT_MAX_OPTIONS = 12


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


@dataclass(frozen=True, slots=True)
class RefereeLine:
    original_text: str
    food_name: str
    recipe_title: str
    grams: Decimal | None


@dataclass(frozen=True, slots=True)
class Judgement:
    decision: MatchDecision
    verdict: RefereeVerdict | None
    evidence: dict[str, object] | None


class MatchReferee:
    def __init__(
        self,
        decisions: DecisionAsker,
        *,
        panel: Sequence[str],
        tolerance_dv: Decimal,
        max_options: int = DEFAULT_MAX_OPTIONS,
    ) -> None:
        self._decisions = decisions
        self._panel = tuple(panel)
        self._tolerance = tolerance_dv
        self._max_options = max_options

    def judge(self, line: RefereeLine, decision: MatchDecision) -> Judgement:
        """Return the decision to store and the evidence to record beside it."""

        unchanged = Judgement(decision, None, None)
        if decision.method == "memory":
            return unchanged
        head = (decision.candidate,) if decision.candidate is not None else ()
        shortlist = list((head + decision.alternatives)[: self._max_options])
        if not shortlist:
            return unchanged
        keys = {f"c{index}": candidate for index, candidate in enumerate(shortlist, start=1)}
        criteria = {key: _describe(candidate.food) for key, candidate in keys.items()}
        criteria[NONE_KEY] = NONE_CRITERION
        state = {
            "recipe": line.recipe_title,
            "ingredient_line": line.original_text,
            "parsed_food_name": line.food_name,
        }
        answers = self._decisions.ask(
            [Ask(Purpose.MATCH_REFEREE, state, {"match": Choice(MATCH_INSTRUCTIONS, criteria)})]
        )[0]
        models = [
            model
            for model in (*self._panel, *answers.by_model)
            if model in answers.by_model and "match" in answers.by_model[model].choices
        ]
        models = list(dict.fromkeys(models))
        if not models:
            return unchanged
        panel = [answers.by_model[model].choices["match"] for model in models]
        options = [
            AssistOption(key, nutrients_per_100g(candidate.food)) for key, candidate in keys.items()
        ]
        current = "c1" if decision.candidate is not None else None
        verdict = judge(
            options, panel, current=current, grams=line.grams, tolerance_dv=self._tolerance
        )
        evidence = self._evidence(verdict, keys, models, answers)
        picked = keys.get(verdict.pick) if verdict.pick else None
        others = tuple(candidate for candidate in shortlist if candidate is not picked)
        if verdict.action is RefereeAction.UPGRADE and picked is not None:
            return Judgement(MatchDecision("matched", METHOD, picked, others), verdict, evidence)
        if verdict.action is RefereeAction.DOWNGRADE:
            alternatives = ((picked,) if picked is not None else ()) + others
            return Judgement(
                MatchDecision("ambiguous", METHOD, None, alternatives), verdict, evidence
            )
        return Judgement(decision, verdict, evidence)

    def _evidence(
        self,
        verdict: RefereeVerdict,
        keys: Mapping[str, FoodCandidate],
        models: Sequence[str],
        answers: Answers,
    ) -> dict[str, object]:
        mean = answers.choice("match") or {}
        picked = keys.get(verdict.pick) if verdict.pick else None
        return {
            "kind": "match_referee",
            "version": PROVENANCE_VERSION,
            "action": verdict.action.value,
            "reason": verdict.reason,
            "models": list(models),
            "toleranceDv": str(self._tolerance),
            "impactDv": str(round(verdict.impact_dv, 6)) if verdict.impact_dv is not None else None,
            "pick": (
                {
                    "foodReferenceId": str(picked.food.id),
                    "description": picked.food.description,
                    "probability": str(round(verdict.pick_probability, 4)),
                }
                if picked is not None
                else None
            ),
            "noneProbability": str(round(mean.get(NONE_KEY, Decimal(0)), 4)),
            "probabilities": [
                {
                    "foodReferenceId": str(keys[key].food.id),
                    "probability": str(round(probability, 4)),
                }
                for key, probability in sorted(mean.items(), key=lambda item: item[1], reverse=True)
                if key in keys
            ],
        }


def _describe(food: FoodReference) -> str:
    return food.description + (f" [{food.food_category}]" if food.food_category else "")


def nutrients_per_100g(food: FoodReference) -> dict[str, Decimal | None]:
    """Tracked nutrients per 100 g of the food.

    A nutrient USDA does not report counts as 0, the convention the tolerance was validated with
    (research report, section 3). Energy falls back to Atwater factors like the nutrition rollup.
    """

    amounts = {item.nutrient_code: item for item in food.nutrients}
    scale = Decimal(100) / food.basis_grams

    def first(codes: Sequence[str]) -> Decimal | None:
        for code in codes:
            item = amounts.get(code)
            if item is not None and item.amount is not None:
                return item.amount * scale
        return None

    values: dict[str, Decimal | None] = {
        name: first(CORE_NUTRIENT_CODES[name])
        for name in ("calories_kcal", "protein_g", "fat_g", "carbohydrate_g")
    }
    for name in ("sodium_mg", "vitamin_c_mg"):
        mapping = USDA_MICRONUTRIENT_MANIFEST[name]
        by_key = next(
            (
                item.amount
                for item in food.nutrients
                if item.canonical_key == name and item.amount is not None
            ),
            None,
        )
        found = by_key * scale if by_key is not None else None
        values[name] = (
            found
            if found is not None
            else first((str(mapping.fdc_nutrient_id), mapping.legacy_number))
        )
    if values["calories_kcal"] is None and None not in (
        values["protein_g"],
        values["carbohydrate_g"],
        values["fat_g"],
    ):
        values["calories_kcal"] = (
            Decimal(4) * (values["protein_g"] or Decimal(0))
            + Decimal(4) * (values["carbohydrate_g"] or Decimal(0))
            + Decimal(9) * (values["fat_g"] or Decimal(0))
        )
    return {name: values.get(name) or Decimal(0) for name in TRACKED_DAILY_VALUES}
