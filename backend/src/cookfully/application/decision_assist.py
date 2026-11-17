"""Optional decision-model assist for ingredient-to-food matching.

The deterministic matcher always runs first. When the owner enables the assist, the candidate
foods it produced are re-ranked by a decision model and the model's pick replaces the
deterministic result only when the impact-aware rule in ``domain.decision_assist`` says the
remaining uncertainty cannot move the recipe's nutrition. Everything else, including every failure,
keeps the deterministic result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from cookfully.domain.decision_assist import (
    NONE_KEY,
    TRACKED_DAILY_VALUES,
    AssistAction,
    AssistOption,
    AssistVerdict,
    evaluate,
)
from cookfully.domain.decisions import Answers, Ask, Choice, Purpose
from cookfully.domain.ingredient_nutrition.matching import FoodCandidate
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
PROVENANCE_VERSION = "decision-assist-v1"


DEFAULT_MAX_OPTIONS = 12


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


@dataclass(frozen=True, slots=True)
class AssistLine:
    original_text: str
    food_name: str
    recipe_title: str
    grams: Decimal | None


@dataclass(frozen=True, slots=True)
class AssistOutcome:
    candidate: FoodCandidate
    verdict: AssistVerdict
    evidence: dict[str, object]


class DecisionAssist:
    def __init__(
        self,
        decisions: DecisionAsker,
        *,
        tolerance_dv: Decimal,
        max_options: int = DEFAULT_MAX_OPTIONS,
    ) -> None:
        self._decisions = decisions
        self._tolerance = tolerance_dv
        self._max_options = max_options

    def resolve(
        self, line: AssistLine, candidates: Sequence[FoodCandidate]
    ) -> AssistOutcome | None:
        """Return the candidate to apply, or ``None`` to keep the deterministic result."""

        shortlist = list(candidates[: self._max_options])
        if not shortlist:
            return None
        keys = {f"c{index}": candidate for index, candidate in enumerate(shortlist, start=1)}
        criteria = {key: _describe(candidate.food) for key, candidate in keys.items()}
        criteria[NONE_KEY] = NONE_CRITERION
        state = {
            "recipe": line.recipe_title,
            "ingredient_line": line.original_text,
            "parsed_food_name": line.food_name,
        }
        answers = self._decisions.ask(
            [
                Ask(
                    Purpose.MATCH_REFEREE,
                    state,
                    {"match": Choice(MATCH_INSTRUCTIONS, criteria)},
                )
            ]
        )[0]
        probabilities = answers.choice("match")
        if not probabilities:
            return None
        options = [
            AssistOption(key, nutrients_per_100g(candidate.food)) for key, candidate in keys.items()
        ]
        verdict = evaluate(options, probabilities, grams=line.grams, tolerance_dv=self._tolerance)
        if verdict.action is not AssistAction.AUTO_RESOLVE or verdict.top_key is None:
            return None
        chosen = keys[verdict.top_key]
        return AssistOutcome(
            chosen, verdict, self._evidence(verdict, keys, tuple(answers.by_model))
        )

    def _evidence(
        self,
        verdict: AssistVerdict,
        keys: Mapping[str, FoodCandidate],
        models: tuple[str, ...],
    ) -> dict[str, object]:
        return {
            "kind": "decision_assist",
            "version": PROVENANCE_VERSION,
            "model": models[0] if models else None,
            "models": list(models),
            "toleranceDv": str(self._tolerance),
            "topProbability": str(round(verdict.top_probability, 4)),
            "expectedErrorDv": {
                name: str(round(value, 6)) for name, value in verdict.expected_error_dv.items()
            },
            "probabilities": [
                {
                    "foodReferenceId": str(keys[key].food.id),
                    "probability": str(round(probability, 4)),
                }
                for key, probability in sorted(
                    verdict.probabilities.items(), key=lambda item: item[1], reverse=True
                )
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
