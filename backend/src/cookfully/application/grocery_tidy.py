"""Grocery tidy: merge synonyms, assign store aisles and mark likely staples.

Run when a grocery list is generated. The panel answers per distinct food name; answers are cached
by name (and, for merges, by the list of other names), so repeat items cost nothing. The owner's
overrides in ``grocery_tidy_memories`` always win: a remembered aisle or staple mark is used as is,
and a "keep separate" veto stops a merge from happening again. Quantities are still only summed
when units are compatible, by the deterministic aggregator.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from cookfully.domain.decisions import Answers, Ask, Check, Choice, Purpose

NONE_KEY = "none"

AISLES: Mapping[str, str] = {
    "produce": "Fresh fruit, vegetables and herbs",
    "meat_seafood": "Meat, poultry and seafood",
    "dairy_eggs": "Milk, cheese, yogurt, butter and eggs",
    "bakery": "Bread, tortillas and baked goods",
    "pantry": "Dry goods, cans, oils, sauces and baking supplies",
    "spices": "Spices, dried herbs and seasonings",
    "frozen": "Frozen food",
    "drinks": "Drinks",
    "other": "Anything else",
}
MERGE_THRESHOLD = Decimal("0.5")
AISLE_THRESHOLD = Decimal("0.5")
STAPLE_THRESHOLD = Decimal("0.3")
MAX_MERGE_OPTIONS = 120

MERGE_INSTRUCTIONS = (
    "Is grocery_item the same thing to buy as one of the listed items, only named differently "
    "(scallions and green onions, cilantro and coriander leaves)? Answer none unless a shopper "
    "would buy exactly the same product for both."
)
AISLE_INSTRUCTIONS = "In which part of a typical supermarket would you find this grocery item?"
STAPLE_INSTRUCTIONS = (
    "Is this a pantry staple most home cooks already have and rarely need to buy for one recipe "
    "(salt, pepper, cooking oil, common spices, sugar, flour)?"
)


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


@dataclass(frozen=True, slots=True)
class TidyLabels:
    aisle: str | None
    staple: bool | None


def synonym_map(
    decisions: DecisionAsker,
    names: Sequence[str],
    vetoes: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, str]:
    """Map names to the name they merge into (only names that merge appear).

    A name merges into another only when every model agrees with mean probability at least
    ``MERGE_THRESHOLD``, the target does not itself merge elsewhere, and the owner has not said to
    keep the two separate. Merges point at the alphabetically first name of a group, so the result
    does not depend on order.
    """

    distinct = sorted(dict.fromkeys(name for name in names if name))
    if len(distinct) < 2 or len(distinct) > MAX_MERGE_OPTIONS:
        return {}
    veto = vetoes or {}
    asks = []
    option_sets: list[dict[str, str]] = []
    for name in distinct:
        options = {f"o{index}": other for index, other in enumerate(distinct) if other != name}
        option_sets.append(options)
        asks.append(
            Ask(
                Purpose.GROCERY_TIDY,
                {"grocery_item": name},
                {
                    "same": Choice(
                        MERGE_INSTRUCTIONS,
                        {**options, NONE_KEY: "None of these: it is a different item."},
                    )
                },
            )
        )
    pairs: dict[str, str] = {}
    for name, options, answers in zip(distinct, option_sets, decisions.ask(asks), strict=True):
        top = answers.top("same")
        probabilities = answers.choice("same") or {}
        if top is None or top == NONE_KEY or not answers.agree("same"):
            continue
        if probabilities.get(top, Decimal(0)) < MERGE_THRESHOLD:
            continue
        other = options[top]
        if other in veto.get(name, frozenset()) or name in veto.get(other, frozenset()):
            continue
        pairs[name] = other
    # Groups of mutually merging names collapse onto their alphabetically first member.
    result: dict[str, str] = {}
    for name, other in pairs.items():
        target = min(name, other)
        if name != target:
            result[name] = target
        elif pairs.get(other) == name:
            result[other] = target
    return {name: target for name, target in result.items() if target not in result}


def classify(decisions: DecisionAsker, names: Sequence[str]) -> dict[str, TidyLabels]:
    distinct = sorted(dict.fromkeys(name for name in names if name))
    asks = [
        Ask(
            Purpose.GROCERY_TIDY,
            {"grocery_item": name},
            {
                "aisle": Choice(AISLE_INSTRUCTIONS, AISLES),
                "staple": Check(
                    STAPLE_INSTRUCTIONS, "A staple most cooks have.", "Usually bought."
                ),
            },
        )
        for name in distinct
    ]
    result: dict[str, TidyLabels] = {}
    for name, answers in zip(distinct, decisions.ask(asks), strict=True):
        aisle = answers.top("aisle")
        aisle_probability = (answers.choice("aisle") or {}).get(aisle or "", Decimal(0))
        staple = answers.check("staple")
        result[name] = TidyLabels(
            aisle if aisle is not None and aisle_probability >= AISLE_THRESHOLD else None,
            None if staple is None else staple >= STAPLE_THRESHOLD,
        )
    return result
