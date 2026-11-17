"""Ingredient substitutions: a fixed table of swaps and ratios, ranked by decision models.

The table is the only source of candidates and amounts; a decision model only judges whether each
candidate suits a particular recipe ("milk and vinegar for buttermilk: fine in pancakes, poor in a
dressing"). Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from cookfully.domain.avoid_list import AvoidLine, find_avoided

SHOW_THRESHOLD = Decimal("0.5")


@dataclass(frozen=True, slots=True)
class Substitute:
    name: str
    amount: str
    """How much to use, relative to the original."""
    note: str = ""


TABLE: Mapping[str, tuple[Substitute, ...]] = {
    "buttermilk": (
        Substitute(
            "Milk with lemon juice or vinegar",
            "1 cup milk + 1 tbsp acid per cup",
            "Rest 5 minutes.",
        ),
        Substitute("Plain yogurt thinned with milk", "3/4 cup yogurt + 1/4 cup milk per cup"),
        Substitute("Kefir", "Same amount"),
    ),
    "butter": (
        Substitute("Olive oil", "3/4 the amount", "Best for sautéing and savoury baking."),
        Substitute("Coconut oil", "Same amount", "Solid at room temperature, like butter."),
        Substitute("Ghee", "Same amount"),
    ),
    "egg": (
        Substitute("Flax egg", "1 tbsp ground flaxseed + 3 tbsp water per egg", "Rest 10 minutes."),
        Substitute(
            "Unsweetened applesauce", "1/4 cup per egg", "Adds moisture and some sweetness."
        ),
        Substitute("Mashed banana", "1/4 cup per egg", "Adds banana flavour."),
    ),
    "sour cream": (
        Substitute("Greek yogurt", "Same amount"),
        Substitute("Crème fraîche", "Same amount"),
    ),
    "heavy cream": (
        Substitute(
            "Milk with melted butter", "3/4 cup milk + 1/4 cup butter per cup", "Will not whip."
        ),
        Substitute("Full-fat coconut milk", "Same amount"),
    ),
    "milk": (
        Substitute("Oat milk", "Same amount"),
        Substitute("Soy milk", "Same amount"),
        Substitute("Water with a little butter", "Same amount of water + 1 tbsp butter per cup"),
    ),
    "yogurt": (
        Substitute("Sour cream", "Same amount"),
        Substitute("Buttermilk", "Same amount", "Thinner."),
    ),
    "mayonnaise": (
        Substitute("Greek yogurt", "Same amount", "Tangier and lighter."),
        Substitute("Mashed avocado", "Same amount"),
    ),
    "white wine": (
        Substitute(
            "Chicken or vegetable stock with a splash of vinegar",
            "Same amount + 1 tsp vinegar per cup",
        ),
        Substitute("White grape juice with lemon", "Same amount + 1 tsp lemon juice per cup"),
    ),
    "red wine": (
        Substitute(
            "Beef or vegetable stock with red wine vinegar", "Same amount + 1 tbsp vinegar per cup"
        ),
        Substitute("Unsweetened grape or cranberry juice", "Same amount"),
    ),
    "brown sugar": (
        Substitute("White sugar with molasses", "1 cup sugar + 1 tbsp molasses per cup"),
        Substitute("Coconut sugar", "Same amount"),
    ),
    "honey": (
        Substitute("Maple syrup", "Same amount"),
        Substitute("Agave syrup", "Same amount"),
    ),
    "maple syrup": (
        Substitute("Honey", "Same amount"),
        Substitute("Brown sugar with water", "3/4 cup sugar + 1/4 cup water per cup"),
    ),
    "cornstarch": (
        Substitute("All-purpose flour", "Twice the amount"),
        Substitute("Arrowroot", "Same amount"),
    ),
    "self raising flour": (
        Substitute(
            "All-purpose flour with baking powder",
            "1 cup flour + 1 1/2 tsp baking powder + 1/4 tsp salt",
        ),
    ),
    "breadcrumb": (
        Substitute("Crushed crackers", "Same amount"),
        Substitute("Rolled oats", "Same amount", "Pulse briefly for a finer crumb."),
        Substitute("Panko", "Same amount"),
    ),
    "lemon juice": (
        Substitute("Lime juice", "Same amount"),
        Substitute("White wine vinegar", "Half the amount"),
    ),
    "lime juice": (Substitute("Lemon juice", "Same amount"),),
    "shallot": (
        Substitute("Onion", "Same amount, finely chopped", "Add a little garlic for depth."),
    ),
    "garlic": (Substitute("Garlic powder", "1/8 tsp per clove"),),
    "cilantro": (
        Substitute("Flat-leaf parsley", "Same amount", "Add lime zest for brightness."),
        Substitute("Basil", "Same amount", "Works in Thai-style dishes."),
    ),
    "parmesan": (
        Substitute("Pecorino romano", "Same amount", "Saltier."),
        Substitute("Grana padano", "Same amount"),
        Substitute("Nutritional yeast", "Half the amount", "Dairy-free."),
    ),
    "soy sauce": (
        Substitute("Tamari", "Same amount", "Usually gluten-free."),
        Substitute("Coconut aminos", "Same amount", "Less salty and slightly sweet."),
    ),
    "rice vinegar": (
        Substitute("Apple cider vinegar", "Same amount"),
        Substitute("White wine vinegar", "Same amount"),
    ),
    "fresh basil": (Substitute("Dried basil", "1/3 the amount"),),
    "fresh thyme": (Substitute("Dried thyme", "1/3 the amount"),),
    "fresh oregano": (Substitute("Dried oregano", "1/3 the amount"),),
    "baking powder": (
        Substitute(
            "Baking soda with cream of tartar", "1/4 tsp soda + 1/2 tsp cream of tartar per tsp"
        ),
    ),
    "chicken stock": (
        Substitute("Vegetable stock", "Same amount"),
        Substitute("Water with bouillon", "Same amount"),
    ),
    "beef stock": (Substitute("Mushroom or vegetable stock", "Same amount"),),
    "ground beef": (
        Substitute("Ground turkey", "Same amount", "Leaner; add a little oil."),
        Substitute("Cooked lentils", "Same amount", "Vegetarian."),
    ),
    "rice": (
        Substitute("Quinoa", "Same amount"),
        Substitute("Cauliflower rice", "Same amount", "Lighter, cooks in minutes."),
    ),
}


def table_key(line: str) -> str | None:
    """The table entry a line names, preferring the longest (most specific) match."""

    keys = sorted(TABLE, key=len, reverse=True)
    hits = find_avoided([AvoidLine(uuid4(), line)], keys)
    if not hits:
        return None
    return max((hit.item for hit in hits), key=len)


@dataclass(frozen=True, slots=True)
class RankedSubstitute:
    substitute: Substitute
    probability: Decimal | None


def rank(
    candidates: Sequence[Substitute], probabilities: Sequence[Decimal | None]
) -> tuple[RankedSubstitute, ...]:
    """Order by probability and hide unlikely swaps; with no answers keep table order, unranked."""

    if all(probability is None for probability in probabilities):
        return tuple(RankedSubstitute(item, None) for item in candidates)
    ranked = [
        RankedSubstitute(item, probability)
        for item, probability in zip(candidates, probabilities, strict=True)
        if probability is not None and probability >= SHOW_THRESHOLD
    ]
    ranked.sort(key=lambda entry: entry.probability or Decimal(0), reverse=True)
    return tuple(ranked)
