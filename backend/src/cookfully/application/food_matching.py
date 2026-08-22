from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from difflib import SequenceMatcher
from typing import cast
from uuid import UUID

from cookfully.domain.common import NUTRIENT_SCALE, quantize_decimal
from cookfully.domain.food_semantics import (
    Compatibility,
    FoodSemanticProfile,
    compare_compatibility,
    profile_from_text,
)
from cookfully.infrastructure.models.nutrition import IngredientMatch
from cookfully.infrastructure.models.reference_foods import FoodReference
from cookfully.infrastructure.repositories.nutrition import NutritionRepository
from cookfully.infrastructure.semantic_embeddings import (
    Embedding,
    HashingTextEmbedder,
    TextEmbedder,
    cosine_similarity,
)

ALIASES = {
    "scallion": "green onion",
    "garbanzo": "chickpea",
    "caster sugar": "sugar",
    "confectioners sugar": "powdered sugar",
    "bell pepper": "sweet pepper",
    # Recipe authors commonly use “super firm” for the same low-moisture tofu
    # category USDA describes as “extra firm”. Prefer the generic reference over
    # a branded product that happens to contain the marketing phrase verbatim.
    "super firm tofu": "extra firm tofu",
}

# Tokens that signal a processed product form, a flavour variant, or a plant part
# that is not the expected edible portion. Each carries -0.05 when the token is
# *absent* from the query because the ingredient name alone implies the base staple,
# not a breaded/dried/juice/flavoured/leaf form. Tokens in the query are never
# penalised ("peanut butter" -> "butter" is safe).
_FORM_TOKENS = frozenset(
    {
        "breaded",
        "candied",
        "canned",
        "chip",
        "dehydrated",
        "deli",
        "dried",
        "dry",
        "flour",
        "fried",
        "glazed",
        "juice",
        "microwaved",
        "nugget",
        "pancake",
        "powder",
        "powdered",
        "puff",
        "roasted",
        "roll",
        "salad",
        "scrambled",
        "seasoned",
        "smoked",
        "souffle",
        "strip",
        "tender",
        "waffle",
    }
)
_FLAVOR_TOKENS = frozenset(
    {
        "barbecue",
        "bbq",
        "blueberry",
        "cherry",
        "chocolate",
        "cinnamon",
        "flavor",
        "flavored",
        "honey",
        "lemon",
        "lime",
        "maple",
        "mesquite",
        "orange",
        "peach",
        "raspberry",
        "strawberry",
        "vanilla",
    }
)
_PART_TOKENS = frozenset({"leave", "peel", "seed", "stalk", "stem"})
_PENALTY_TOKENS = _FORM_TOKENS | _FLAVOR_TOKENS | _PART_TOKENS


def normalize_food(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()
    return ALIASES.get(normalized, normalized)


@dataclass(frozen=True, slots=True)
class FoodCandidate:
    food: FoodReference
    score: Decimal
    compatibility: Compatibility = Compatibility.COMPATIBLE
    reasons: tuple[str, ...] = ()
    semantic_similarity: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class MatchDecision:
    status: str
    method: str
    candidate: FoodCandidate | None
    alternatives: tuple[FoodCandidate, ...]


class FoodMatcher:
    def __init__(
        self,
        repository: NutritionRepository,
        *,
        embedder: TextEmbedder | None = None,
        candidate_pool_limit: int | None = None,
    ) -> None:
        self.repository = repository
        self._embedder = embedder or HashingTextEmbedder()
        self._candidate_pool_limit = candidate_pool_limit
        self._food_pool: tuple[FoodReference, ...] | None = None
        self._food_embeddings: dict[UUID, Embedding] = {}
        self._food_profiles: dict[UUID, FoodSemanticProfile] = {}

    def candidates(self, food_name: str, *, limit: int = 10) -> tuple[FoodCandidate, ...]:
        concept = profile_from_text(food_name)
        query = _rank_query(food_name) or _semantic_query(concept) or normalize_food(food_name)
        foods = self._food_candidates(query, limit=limit)
        ranked = []
        query_embedding = self._embedder.embed((food_name,))[0]
        for food in foods:
            candidate_profile = self._food_profile(food)
            compatibility = compare_compatibility(concept, candidate_profile)
            if compatibility.compatibility is Compatibility.CONTRADICTORY:
                continue
            similarity = quantize_decimal(
                Decimal(str(self._embedder_similarity(query_embedding, food))), NUTRIENT_SCALE
            )
            ranked.append(
                FoodCandidate(
                    food,
                    self._score(query, food, concept),
                    compatibility.compatibility,
                    compatibility.reasons,
                    similarity,
                )
            )
        ranked.sort(
            key=lambda item: (-item.score, -item.semantic_similarity, item.food.external_id)
        )
        deduped: list[FoodCandidate] = []
        seen: set[str] = set()
        for cand in ranked:
            norm = normalize_food(cand.food.normalized_name)
            if norm in seen:
                continue
            seen.add(norm)
            deduped.append(cand)
        return tuple(deduped[:limit])

    def decide(
        self,
        food_name: str,
        *,
        preferred_food: FoodReference | None = None,
    ) -> MatchDecision:
        if preferred_food is not None:
            concept = profile_from_text(food_name)
            compatibility = compare_compatibility(
                concept, profile_from_text(preferred_food.description)
            )
            if compatibility.compatibility is not Compatibility.CONTRADICTORY:
                return MatchDecision(
                    "matched",
                    "memory",
                    FoodCandidate(
                        preferred_food,
                        Decimal("1.000000"),
                        compatibility.compatibility,
                        compatibility.reasons,
                        Decimal("1.000000"),
                    ),
                    (),
                )
        candidates = self.candidates(food_name)
        if not candidates or candidates[0].score < Decimal("0.650000"):
            return MatchDecision("unmatched", "ranked", None, candidates)
        top = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else Decimal(0)
        if (
            top.compatibility is Compatibility.COMPATIBLE
            and top.score >= Decimal("0.800000")
            and top.score - second_score > Decimal(0)
        ):
            exact = normalize_food(top.food.normalized_name) == normalize_food(food_name)
            return MatchDecision("matched", "exact" if exact else "ranked", top, candidates[1:])
        return MatchDecision("ambiguous", "ranked", None, candidates)

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
    def _score(
        query: str,
        food: FoodReference,
        concept: FoodSemanticProfile | None = None,
    ) -> Decimal:
        normalized = normalize_food(food.normalized_name)
        candidate_concept = profile_from_text(food.description)
        semantic_identity_bonus = Decimal(0)
        if concept is not None and concept.canonical_identity:
            if concept.canonical_identity == candidate_concept.canonical_identity:
                semantic_identity_bonus = Decimal("0.150000")
        if query == normalized:
            return Decimal("1.000000")
        query_tokens = _tokens(query)
        candidate_tokens = _tokens(normalized)
        query_set = set(query_tokens)
        candidate_set = set(candidate_tokens)
        intersection = query_set & candidate_set
        if not intersection:
            ratio = Decimal(str(SequenceMatcher(None, query, normalized).ratio()))
            return quantize_decimal(ratio * Decimal("0.500000"), NUTRIENT_SCALE)
        if len(intersection) < len(query_set):
            if semantic_identity_bonus:
                missing_query = len(query_set - candidate_set)
                candidate_extra = candidate_set - query_set
                penalty_hits = candidate_extra & _PENALTY_TOKENS
                penalty = Decimal("0.050000") * len(penalty_hits) + Decimal("0.010000") * (
                    len(candidate_extra) - len(penalty_hits)
                )
                score = (
                    Decimal("0.750000")
                    + semantic_identity_bonus
                    - Decimal("0.020000") * missing_query
                    - penalty
                )
                return quantize_decimal(
                    max(Decimal("0.650000"), min(score, Decimal("0.799999"))),
                    NUTRIENT_SCALE,
                )
            aligned = Decimal(len(intersection)) / Decimal(len(query_set))
            jaccard = Decimal(len(intersection)) / Decimal(
                len(query_set) + len(candidate_set) - len(intersection)
            )
            score = min(
                Decimal("0.620000") * aligned + Decimal("0.380000") * jaccard,
                Decimal("0.600000"),
            )
            return quantize_decimal(score, NUTRIENT_SCALE)
        lead = (
            Decimal("0.120000")
            if candidate_tokens and candidate_tokens[0] in query_set
            else Decimal(0)
        )
        block = (
            Decimal("0.080000")
            if len(query_set) >= 2 and _has_block(query_set, candidate_tokens)
            else Decimal(0)
        )
        head = Decimal("0.050000") if _head_matches(query_tokens, food.description) else Decimal(0)
        unmatched = candidate_set - query_set
        penalty_hits = unmatched & _PENALTY_TOKENS
        penalty = Decimal("0.050000") * len(penalty_hits) + Decimal("0.010000") * (
            len(unmatched) - len(penalty_hits)
        )
        base_score = Decimal("0.650000") if semantic_identity_bonus else Decimal("0.750000")
        score = base_score + lead + block + head + semantic_identity_bonus - penalty
        clamped = max(Decimal(0), min(score, Decimal(1)))
        return quantize_decimal(clamped, NUTRIENT_SCALE)

    def _embedder_similarity(
        self, query_embedding: tuple[float, ...], food: FoodReference
    ) -> float:
        vector = self._food_embeddings.get(food.id)
        if vector is None:
            vector = self._embedder.embed((food.description,))[0]
        return cosine_similarity(query_embedding, vector)

    def _food_candidates(self, query: str, *, limit: int) -> list[FoodReference]:
        if self._candidate_pool_limit is not None:
            shortlist = getattr(self.repository, "search_foods_for_matching", None)
            if callable(shortlist):
                return cast(Callable[..., list[FoodReference]], shortlist)(
                    query,
                    limit=max(limit, self._candidate_pool_limit),
                )
            return self.repository.search_foods(
                query,
                limit=max(limit, self._candidate_pool_limit),
            )
        list_active = getattr(self.repository, "list_active_foods", None)
        if not callable(list_active):
            return self.repository.search_foods(query, limit=max(limit * 3, 20))
        if self._food_pool is None:
            self._food_pool = tuple(list_active())
            vectors = self._embedder.embed(tuple(food.description for food in self._food_pool))
            self._food_embeddings = {
                food.id: vector for food, vector in zip(self._food_pool, vectors, strict=True)
            }
        return list(self._food_pool)

    def _food_profile(self, food: FoodReference) -> FoodSemanticProfile:
        profile = self._food_profiles.get(food.id)
        if profile is None:
            profile = profile_from_text(food.description)
            self._food_profiles[food.id] = profile
        return profile


def _semantic_query(concept: FoodSemanticProfile) -> str:
    values = [concept.canonical_identity, concept.part, concept.form]
    return " ".join(value for value in values if value and value != "whole_food")


def _rank_query(value: str) -> str:
    normalized = normalize_food(value)
    return " ".join(token for token in normalized.split() if not token[:1].isdigit())


def _tokens(value: str) -> list[str]:
    return [_singular(token) for token in normalize_food(value).split() if token]


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and len(word) > 3 and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _has_block(query_set: set[str], candidate_tokens: list[str]) -> bool:
    """True when every query token appears inside one contiguous candidate window.

    Word order is irrelevant because USDA descriptions invert English noun phrases
    ("Yogurt, Greek, ..." for "greek yogurt"), but adjacency still signals that the
    tokens name one food rather than scattered modifiers.
    """

    size = len(query_set)
    return any(
        query_set <= set(candidate_tokens[index : index + size])
        for index in range(len(candidate_tokens) - size + 1)
    )


def _head_matches(query_tokens: list[str], description: str) -> bool:
    """True when the query names the candidate's food identity.

    USDA descriptions put the food identity before the first comma ("Milk, whole, ..."),
    while compact Foundation names have no comma and the whole name is the identity. The
    query's final token is the English head noun, so matching it against the identity
    phrase separates "Rice, brown" from "Rice flour, brown" for a "brown rice" query.
    """

    if not query_tokens:
        return False
    head_tokens = _tokens(description.split(",", 1)[0])
    if not head_tokens:
        return False
    return head_tokens[-1] == query_tokens[-1] or set(query_tokens) <= set(head_tokens)
