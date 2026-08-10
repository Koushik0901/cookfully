from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from uuid import UUID

from vigor_vine.domain.common import NUTRIENT_SCALE, quantize_decimal
from vigor_vine.infrastructure.models.nutrition import IngredientMatch
from vigor_vine.infrastructure.models.reference_foods import FoodReference
from vigor_vine.infrastructure.repositories.nutrition import NutritionRepository

ALIASES = {
    "scallion": "green onion",
    "garbanzo": "chickpea",
    "caster sugar": "sugar",
    "confectioners sugar": "powdered sugar",
    "bell pepper": "sweet pepper",
}


def normalize_food(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()
    return ALIASES.get(normalized, normalized)


@dataclass(frozen=True, slots=True)
class FoodCandidate:
    food: FoodReference
    score: Decimal


@dataclass(frozen=True, slots=True)
class MatchDecision:
    status: str
    method: str
    candidate: FoodCandidate | None
    alternatives: tuple[FoodCandidate, ...]


class FoodMatcher:
    def __init__(self, repository: NutritionRepository) -> None:
        self.repository = repository

    def candidates(self, food_name: str, *, limit: int = 10) -> tuple[FoodCandidate, ...]:
        query = normalize_food(food_name)
        foods = self.repository.search_foods(query, limit=max(limit * 3, 20))
        ranked = sorted(
            (FoodCandidate(food, self._score(query, food.normalized_name)) for food in foods),
            key=lambda item: (-item.score, item.food.external_id),
        )
        return tuple(ranked[:limit])

    def decide(self, food_name: str) -> MatchDecision:
        candidates = self.candidates(food_name)
        if not candidates or candidates[0].score < Decimal("0.650000"):
            return MatchDecision("unmatched", "ranked", None, candidates)
        top = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else Decimal(0)
        if top.score < Decimal("0.920000") and top.score - second_score < Decimal("0.050000"):
            return MatchDecision("ambiguous", "ranked", None, candidates)
        method = "exact" if top.score == Decimal(1) else "ranked"
        return MatchDecision("matched", method, top, candidates[1:])

    def activate_manual(
        self,
        ingredient_id: UUID,
        food: FoodReference,
        *,
        input_hash: str,
        grams_min: Decimal | None = None,
        grams_max: Decimal | None = None,
        assumption: str | None = None,
    ) -> IngredientMatch:
        match = IngredientMatch(
            ingredient_id=ingredient_id,
            food_reference_id=food.id,
            status="manual",
            match_method="manual",
            match_score=None,
            grams_min=grams_min,
            grams_max=grams_max,
            conversion_method="manual" if grams_min is not None else None,
            assumption_text=assumption,
            source_release_id=food.dataset.release_id,
            input_hash=input_hash,
            active=True,
        )
        return self.repository.activate_match(match)

    @staticmethod
    def _score(query: str, candidate: str) -> Decimal:
        normalized = normalize_food(candidate)
        if query == normalized:
            return Decimal("1.000000")
        query_tokens = set(query.split())
        candidate_tokens = set(normalized.split())
        union = query_tokens | candidate_tokens
        jaccard = Decimal(len(query_tokens & candidate_tokens)) / Decimal(len(union) or 1)
        sequence = Decimal(str(SequenceMatcher(None, query, normalized).ratio()))
        return quantize_decimal(max(jaccard, sequence), NUTRIENT_SCALE)
