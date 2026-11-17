"""Recipe facets: the tags decision models give a recipe, with deterministic safety checks.

The models answer typed questions about a recipe (diet, cuisine, meal type, effort, active time,
storage, oven). This module owns the vocabulary, turns answers into tags with a probability, and
drops diet tags the ingredient list contradicts: a "vegetarian" tag on a recipe that names chicken
is removed, whatever the model said. A tag is shown at ``SHOW_THRESHOLD`` and worded as certain from
``CONFIDENT_THRESHOLD``.

Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from cookfully.domain.avoid_list import AvoidLine, find_avoided
from cookfully.domain.decisions import Answers

SHOW_THRESHOLD = Decimal("0.5")
CONFIDENT_THRESHOLD = Decimal("0.8")

DIETS: Mapping[str, str] = {
    "vegetarian": "Vegetarian: no meat, poultry, fish or seafood.",
    "vegan": "Vegan: no animal products at all (no meat, fish, dairy, eggs or honey).",
    "gluten_free": "Gluten-free: no wheat, barley, rye or ingredients made from them.",
    "dairy_free": "Dairy-free: no milk, butter, cheese, cream, yogurt or other dairy.",
}
CUISINES: Mapping[str, str] = {
    "italian": "Italian",
    "mexican": "Mexican",
    "chinese": "Chinese",
    "japanese": "Japanese",
    "korean": "Korean",
    "thai": "Thai",
    "indian": "Indian",
    "middle_eastern": "Middle Eastern",
    "mediterranean": "Mediterranean or Greek",
    "french": "French",
    "american": "American",
    "other": "Another cuisine, a mix, or no clear cuisine",
}
MEAL_TYPES: Mapping[str, str] = {
    "breakfast": "Breakfast or brunch",
    "main": "A main course for lunch or dinner",
    "side": "A side dish or salad served with a main",
    "snack": "A snack or appetizer",
    "dessert": "A dessert or sweet baked good",
    "drink": "A drink or smoothie",
    "component": "A sauce, dressing, stock or other component",
}
EFFORT_LEVELS = (
    "Minimal: a few steps, little skill.",
    "Moderate: several steps, some attention.",
    "Involved: many steps, techniques or long attention.",
)
ACTIVE_TIME_LEVELS = (
    "Under 15 minutes of hands-on work.",
    "15 to 30 minutes of hands-on work.",
    "30 to 60 minutes of hands-on work.",
    "More than an hour of hands-on work.",
)
STORAGE: Mapping[str, tuple[str, str, str]] = {
    # key: (question, yes, no)
    "keeps_4_days": (
        "Does this dish keep well in the fridge for about four days?",
        "Keeps well for about four days.",
        "Best eaten within a day or two.",
    ),
    "freezes_well": (
        "Does this dish freeze and thaw well?",
        "Freezes well.",
        "Does not freeze well.",
    ),
    "reheats_well": (
        "Does this dish reheat well?",
        "Reheats well.",
        "Is best fresh or served cold.",
    ),
    "needs_oven": (
        "Does making this recipe need an oven?",
        "Needs an oven.",
        "No oven needed.",
    ),
}

# Ingredient words that rule a diet out (group names from ``domain.avoid_list``).
_CONFLICTS: Mapping[str, tuple[str, ...]] = {
    "vegetarian": ("meat", "fish", "shellfish"),
    "vegan": ("meat", "fish", "shellfish", "dairy", "egg", "honey"),
    "gluten_free": ("gluten",),
    "dairy_free": ("dairy",),
}


@dataclass(frozen=True, slots=True)
class FacetTag:
    key: str
    """e.g. ``vegetarian``, ``cuisine:italian``, ``meal:main``, ``effort:minimal``."""
    probability: Decimal

    @property
    def confident(self) -> bool:
        return self.probability >= CONFIDENT_THRESHOLD


def interpret(answers: Answers, ingredient_lines: Sequence[str]) -> tuple[FacetTag, ...]:
    """Tags to show, in a stable order. Empty answers give no tags."""

    tags: list[FacetTag] = []
    contradicted = _contradicted_diets(ingredient_lines)
    for diet in DIETS:
        probability = answers.check(f"diet_{diet}")
        if probability is not None and probability >= SHOW_THRESHOLD and diet not in contradicted:
            tags.append(FacetTag(diet, round(probability, 4)))
    for question, prefix in (("cuisine", "cuisine"), ("meal_type", "meal")):
        top = answers.top(question)
        probabilities = answers.choice(question) or {}
        if top and top != "other" and probabilities.get(top, Decimal(0)) >= SHOW_THRESHOLD:
            tags.append(FacetTag(f"{prefix}:{top}", round(probabilities[top], 4)))
    effort = answers.score("effort")
    if effort is not None:
        level = ("minimal", "moderate", "involved")[_bucket(effort, 3)]
        tags.append(FacetTag(f"effort:{level}", round(_bucket_confidence(effort, 3), 4)))
    active = answers.score("active_time")
    if active is not None:
        level = ("under_15", "15_30", "30_60", "over_60")[_bucket(active, 4)]
        tags.append(FacetTag(f"time:{level}", round(_bucket_confidence(active, 4), 4)))
    for key in STORAGE:
        probability = answers.check(key)
        if probability is not None and probability >= SHOW_THRESHOLD:
            tags.append(FacetTag(key, round(probability, 4)))
    keys = {tag.key for tag in tags}
    if "time:under_15" in keys or {"effort:minimal", "time:15_30"} <= keys:
        tags.append(FacetTag("weeknight", Decimal(1)))
    return tuple(tags)


def _contradicted_diets(lines: Sequence[str]) -> set[str]:
    named = {
        warning.item
        for warning in find_avoided(
            [AvoidLine(uuid4(), line) for line in lines],
            sorted({group for groups in _CONFLICTS.values() for group in groups}),
        )
    }
    return {diet for diet, groups in _CONFLICTS.items() if named & set(groups)}


def _bucket(score: Decimal, levels: int) -> int:
    """Nearest level for a normalized score in [0, 1]."""

    return min(levels - 1, max(0, int(score * (levels - 1) + Decimal("0.5"))))


def _bucket_confidence(score: Decimal, levels: int) -> Decimal:
    """1 at a level's centre, falling to 0.5 halfway to the next level."""

    position = score * (levels - 1)
    distance = abs(position - _bucket(score, levels))
    return Decimal(1) - distance
