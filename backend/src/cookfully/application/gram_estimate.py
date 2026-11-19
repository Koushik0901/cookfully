"""Model-estimated weight for counted ingredients, so "1 medium onion" still has nutrition.

Only ingredients whose unit is a plain count and that have no weight on record are asked about.
The result is a gram *range* from the panel's distribution; the conversion is labelled
``count_weight_model`` so the roll-up and the UI show it as an estimate, and an owner correction
or a recorded owner-food serving always wins over it.
"""

from __future__ import annotations

from decimal import Decimal

from cookfully.domain.count_weights import COUNT_WEIGHT_BUCKETS, weight_range
from cookfully.domain.decisions import Ask, Choice, DecisionAsker, Purpose

INSTRUCTIONS = (
    "How much does ONE of this ingredient weigh, as written (size words such as small, medium or "
    "large count), edible weight as used in the recipe?"
)
MAX_TEXT_CHARS = 200


def item_weight_range(
    decisions: DecisionAsker, ingredient_text: str, food_name: str
) -> tuple[Decimal, Decimal] | None:
    """Grams for one counted item as ``(low, high)``, or ``None`` when the panel gives nothing."""

    text = " ".join(ingredient_text.split())[:MAX_TEXT_CHARS]
    food = " ".join(food_name.split())[:MAX_TEXT_CHARS]
    if not text and not food:
        return None
    [answers] = decisions.ask(
        [
            Ask(
                Purpose.GRAM_ESTIMATE,
                {"ingredient": text, "food": food},
                {
                    "weight": Choice(
                        INSTRUCTIONS,
                        {
                            key: description
                            for key, (_, _, description) in COUNT_WEIGHT_BUCKETS.items()
                        },
                    )
                },
            )
        ]
    )
    probabilities = answers.choice("weight")
    return weight_range(probabilities) if probabilities else None
