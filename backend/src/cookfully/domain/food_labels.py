"""Decision-model labels on reference foods, and how the matcher uses them.

``FoodLabels`` is the read-side view of a stored label set (see ``application.food_labels``).
``label_penalty`` turns confident labels that contradict an ingredient line into a small score
penalty for that candidate food. Only confident labels (``CONFIDENT``) act, and a food without
labels is unaffected, so matching is unchanged until foods are labelled.

Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from cookfully.domain.food_semantics import profile_from_text

CONFIDENT = Decimal("0.7")
STATE_CONTRADICTION = Decimal("0.08")
DEFAULT_STATE_MISMATCH = Decimal("0.04")
FLAVORED_PENALTY = Decimal("0.05")
PROCESSED_PENALTY = Decimal("0.03")
_COOKED_STATES = frozenset({"cooked", "roasted", "fried"})
_FLAVOR_WORDS = frozenset(
    {
        "flavored",
        "flavoured",
        "sweetened",
        "seasoned",
        "honey",
        "chocolate",
        "vanilla",
        "spiced",
        "glazed",
        "candied",
        "barbecue",
        "bbq",
        "salted",
        "smoked",
        "breaded",
        "coated",
    }
)
_PROCESSED_WORDS = frozenset({"mix", "sauce", "frozen", "prepared", "canned", "instant", "brand"})


@dataclass(frozen=True, slots=True)
class FoodLabels:
    """Read-side view of stored labels for the matcher."""

    state: str | None = None
    state_probability: Decimal = Decimal(0)
    kind: str | None = None
    kind_probability: Decimal = Decimal(0)
    flavored: Decimal | None = None

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> FoodLabels:
        def pair(key: str) -> tuple[str | None, Decimal]:
            value = payload.get(key)
            if not isinstance(value, list) or len(value) != 2:
                return None, Decimal(0)
            try:
                return str(value[0]), Decimal(str(value[1]))
            except InvalidOperation:
                return None, Decimal(0)

        state, state_p = pair("state")
        kind, kind_p = pair("kind")
        try:
            flavored = Decimal(str(payload["flavored"])) if "flavored" in payload else None
        except InvalidOperation:
            flavored = None
        return cls(state, state_p, kind, kind_p, flavored)


def label_penalty(food_name: str, labels: FoodLabels | None) -> Decimal:
    """Score penalty for a candidate food whose confident labels contradict the line."""

    if labels is None:
        return Decimal(0)
    words = set(food_name.lower().replace(",", " ").split())
    line_state = profile_from_text(food_name).state
    penalty = Decimal(0)
    if labels.state is not None and labels.state_probability >= CONFIDENT:
        cooked_line_raw_food = line_state in _COOKED_STATES and labels.state == "raw"
        raw_line_cooked_food = line_state == "raw" and labels.state == "cooked"
        if cooked_line_raw_food or raw_line_cooked_food:
            penalty += STATE_CONTRADICTION
        elif line_state is None and labels.state in {"cooked", "canned"}:
            penalty += DEFAULT_STATE_MISMATCH
    if labels.flavored is not None and labels.flavored >= CONFIDENT and not words & _FLAVOR_WORDS:
        penalty += FLAVORED_PENALTY
    if (
        labels.kind in {"processed", "branded"}
        and labels.kind_probability >= CONFIDENT
        and not words & _PROCESSED_WORDS
    ):
        penalty += PROCESSED_PENALTY
    return penalty
