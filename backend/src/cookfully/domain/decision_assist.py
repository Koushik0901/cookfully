"""Impact-aware resolution rule for decision-model answers.

A decision model returns a probability per candidate food. Picking the most likely food is only
safe to automate when being wrong would not change the recipe's nutrition: a tie between two olive
oils is harmless, an uncertain butter is not. The rule here measures that per tracked nutrient as a
share of the daily value, following ``docs/decision-model-experiments/README.md`` (section 4).

The module is pure: no I/O, no framework imports, fixed-precision decimals only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# Daily values (FDA, adult 2,000 kcal reference diet) for the nutrients whose error must stay small.
# A calorie-only rule hides sodium and vitamin C error, so every key here is checked.
TRACKED_DAILY_VALUES: Mapping[str, Decimal] = {
    "calories_kcal": Decimal(2000),
    "protein_g": Decimal(50),
    "fat_g": Decimal(78),
    "carbohydrate_g": Decimal(275),
    "sodium_mg": Decimal(2300),
    "vitamin_c_mg": Decimal(90),
}

# The reserved option meaning "no listed food is acceptable, or this line is not a food".
NONE_KEY = "none"

DEFAULT_TOLERANCE_DV = Decimal("0.02")

_ZERO = Decimal(0)
_ONE = Decimal(1)


class AssistAction(StrEnum):
    AUTO_RESOLVE = "auto_resolve"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class AssistOption:
    """One candidate food with its nutrients per 100 g (``None`` when USDA has no value)."""

    key: str
    nutrients_per_100g: Mapping[str, Decimal | None]


@dataclass(frozen=True, slots=True)
class AssistVerdict:
    action: AssistAction
    reason: str
    top_key: str | None
    top_probability: Decimal
    probabilities: Mapping[str, Decimal]
    expected_error_dv: Mapping[str, Decimal]


def normalize_probabilities(
    raw: Mapping[str, float | Decimal], allowed: Sequence[str]
) -> dict[str, Decimal] | None:
    """Keep only known options, reject malformed values and renormalize to sum to 1.

    Returns ``None`` (fail closed) when nothing usable remains.
    """

    kept: dict[str, Decimal] = {}
    for key, value in raw.items():
        if key not in allowed:
            continue
        try:
            probability = Decimal(str(value))
        except ArithmeticError:
            return None
        if not probability.is_finite() or probability < _ZERO or probability > _ONE:
            return None
        kept[key] = probability
    total = sum(kept.values(), _ZERO)
    if total <= _ZERO:
        return None
    return {key: value / total for key, value in kept.items()}


def evaluate(
    options: Sequence[AssistOption],
    probabilities: Mapping[str, float | Decimal],
    *,
    grams: Decimal | None,
    tolerance_dv: Decimal = DEFAULT_TOLERANCE_DV,
) -> AssistVerdict:
    """Decide whether the model's top option can be applied without a person looking.

    Expected error for a nutrient is
    ``sum(p(option) * |nutrient(option) - nutrient(top)|) * grams / 100`` using the
    model's own probabilities. The line auto-resolves only when it is at most
    ``tolerance_dv`` of the daily value in *every* tracked nutrient. The ``none`` option counts as a
    food with no nutrients. The rule fails closed: a missing quantity, a missing nutrient value on
    any option with probability mass, an unusable distribution or a ``none`` winner all mean review.
    """

    by_key = {option.key: option for option in options}
    allowed = [*by_key, NONE_KEY]
    normalized = normalize_probabilities(probabilities, allowed)
    if normalized is None:
        return _review("unusable_probabilities", None, _ZERO, {}, {})
    top_key = max(normalized, key=lambda key: (normalized[key], key != NONE_KEY))
    top_probability = normalized[top_key]
    if top_key == NONE_KEY:
        return _review("model_rejected_options", top_key, top_probability, normalized, {})
    if grams is None:
        return _review("quantity_unknown", top_key, top_probability, normalized, {})

    top = by_key[top_key]
    errors: dict[str, Decimal] = {}
    for nutrient, daily_value in TRACKED_DAILY_VALUES.items():
        top_amount = top.nutrients_per_100g.get(nutrient)
        if top_amount is None:
            return _review("nutrient_missing", top_key, top_probability, normalized, errors)
        expected = _ZERO
        for key, probability in normalized.items():
            if key == top_key:
                continue
            if key == NONE_KEY:
                other = _ZERO
            else:
                value = by_key[key].nutrients_per_100g.get(nutrient)
                if value is None:
                    return _review("nutrient_missing", top_key, top_probability, normalized, errors)
                other = value
            expected += probability * abs(other - top_amount)
        errors[nutrient] = expected * grams / Decimal(100) / daily_value
    if any(error > tolerance_dv for error in errors.values()):
        return _review(
            "expected_error_above_tolerance", top_key, top_probability, normalized, errors
        )
    return AssistVerdict(
        AssistAction.AUTO_RESOLVE,
        "expected_error_within_tolerance",
        top_key,
        top_probability,
        normalized,
        errors,
    )


def _review(
    reason: str,
    top_key: str | None,
    top_probability: Decimal,
    probabilities: Mapping[str, Decimal],
    errors: Mapping[str, Decimal],
) -> AssistVerdict:
    return AssistVerdict(
        AssistAction.REVIEW, reason, top_key, top_probability, probabilities, errors
    )
