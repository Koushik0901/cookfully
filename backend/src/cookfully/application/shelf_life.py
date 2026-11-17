"""Model-estimated shelf life for pantry items the fixed lifespan table does not know.

The panel picks a lifespan bucket for the item name. Only an agreed, reasonably confident answer is
used; the date is then marked ``expiry_source = "model"`` so the owner can see it was estimated and
edit it. Answers are cached by normalized name, so a repeat item costs nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import build_decisions
from cookfully.domain.decisions import Answers, Ask, Choice, Purpose
from cookfully.domain.expiry_lifespans import SHELF_LIFE_BUCKETS, needs_model_estimate

MIN_PROBABILITY = Decimal("0.5")
INSTRUCTIONS = (
    "Roughly how long does this item usually keep once bought, stored the usual way (fridge for "
    "perishables, cupboard for dry goods)?"
)


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


def estimate_days(decisions: DecisionAsker, display_name: str) -> int | None:
    name = " ".join(display_name.casefold().split())
    if not name or not needs_model_estimate(name):
        return None
    [answers] = decisions.ask(
        [
            Ask(
                Purpose.SHELF_LIFE,
                {"pantry_item": name},
                {
                    "lifespan": Choice(
                        INSTRUCTIONS,
                        {key: description for key, (_, description) in SHELF_LIFE_BUCKETS.items()},
                    )
                },
            )
        ]
    )
    top = answers.top("lifespan")
    probabilities = answers.choice("lifespan") or {}
    if top is None or not answers.agree("lifespan"):
        return None
    if probabilities.get(top, Decimal(0)) < MIN_PROBABILITY:
        return None
    return SHELF_LIFE_BUCKETS[top][0]


def model_expiry(
    session_factory: sessionmaker[Session], display_name: str, today: date
) -> date | None:
    """An estimated expiry date, or ``None`` when the models give no agreed answer."""

    days = estimate_days(build_decisions(session_factory), display_name)
    return today + timedelta(days=days) if days is not None else None
