"""Which recipe ingredients contain something on the owner's avoid list, by their own words.

Deterministic and conservative: an avoided item matches an ingredient line when one of its words (or
a known member of a group such as "shellfish" or "tree nuts") appears in the line, allowing simple
plurals. Hidden ingredients (anchovy in Worcestershire sauce) are left to the model-based check,
which only ever adds warnings to these.

Pure: no I/O.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

# Group names people commonly put on an avoid list, and the words that name their members.
GROUPS: Mapping[str, tuple[str, ...]] = {
    "shellfish": (
        "shrimp",
        "prawn",
        "crab",
        "lobster",
        "crayfish",
        "langoustine",
        "clam",
        "mussel",
        "oyster",
        "scallop",
        "squid",
        "calamari",
        "octopus",
    ),
    "fish": (
        "fish",
        "salmon",
        "tuna",
        "cod",
        "haddock",
        "halibut",
        "trout",
        "sardine",
        "anchovy",
        "mackerel",
        "tilapia",
        "snapper",
        "bass",
        "pollock",
    ),
    "tree nut": (
        "almond",
        "walnut",
        "cashew",
        "pecan",
        "pistachio",
        "hazelnut",
        "macadamia",
        "brazil nut",
        "pine nut",
    ),
    "nut": (
        "almond",
        "walnut",
        "cashew",
        "pecan",
        "pistachio",
        "hazelnut",
        "macadamia",
        "peanut",
        "pine nut",
    ),
    "peanut": ("peanut",),
    "dairy": (
        "milk",
        "cheese",
        "butter",
        "cream",
        "yogurt",
        "yoghurt",
        "ghee",
        "whey",
        "parmesan",
        "mozzarella",
        "cheddar",
        "ricotta",
        "buttermilk",
    ),
    "gluten": (
        "wheat",
        "flour",
        "bread",
        "pasta",
        "barley",
        "rye",
        "couscous",
        "semolina",
        "breadcrumb",
        "panko",
        "spaghetti",
        "noodle",
    ),
    "egg": ("egg",),
    "soy": ("soy", "soya", "tofu", "edamame", "tempeh", "miso"),
    "sesame": ("sesame", "tahini"),
    "pork": ("pork", "bacon", "ham", "prosciutto", "pancetta", "chorizo", "lard", "guanciale"),
    "beef": ("beef", "steak", "brisket", "veal"),
}

# Phrases that contain a member word but do not name that food ("peanut butter" is not dairy).
_FALSE_FRIENDS: Mapping[str, tuple[str, ...]] = {
    "butter": (
        "peanut butter",
        "almond butter",
        "cashew butter",
        "nut butter",
        "apple butter",
        "cocoa butter",
        "shea butter",
        "sunflower butter",
        "butter bean",
    ),
    "milk": ("coconut milk", "almond milk", "oat milk", "soy milk", "rice milk", "cashew milk"),
    "cream": ("cream of tartar", "coconut cream", "ice cream sandwich"),
    "cheese": ("vegan cheese",),
}

_WORD = re.compile(r"[a-z]+")


@dataclass(frozen=True, slots=True)
class AvoidLine:
    ingredient_id: UUID
    text: str


@dataclass(frozen=True, slots=True)
class AvoidWarning:
    ingredient_id: UUID
    item: str
    """The avoid-list entry as the owner wrote it."""
    source: str = "ingredient"
    """``ingredient`` (named in the line) or ``model`` (a decision model suspects it)."""
    probability: Decimal | None = None


def find_avoided(lines: Sequence[AvoidLine], avoid: Iterable[str]) -> tuple[AvoidWarning, ...]:
    """Warnings for each line that names an avoided item, in line then list order."""

    terms = [(item, _terms(item)) for item in avoid if item.strip()]
    warnings: list[AvoidWarning] = []
    for line in lines:
        text = _normalize(line.text)
        for item, words in terms:
            if any(_contains(text, word) for word in words):
                warnings.append(AvoidWarning(line.ingredient_id, item))
    return tuple(warnings)


def _terms(item: str) -> tuple[str, ...]:
    phrase = _singular_phrase(_normalize(item))
    terms = {phrase}
    for group, members in GROUPS.items():
        if phrase in {group, _plural(group)} or phrase == _singular_phrase(group):
            terms.update(members)
    return tuple(sorted(terms))


def _contains(text: str, term: str) -> bool:
    if not term:
        return False
    if term.endswith("y") and len(term) > 2:
        pattern = rf"\b{re.escape(term[:-1])}(?:y|ies)\b"
    else:
        pattern = rf"\b{re.escape(term)}(?:s|es)?\b"
    for match in re.finditer(pattern, text):
        if not _is_false_friend(text, match.start(), term):
            return True
    return False


def _is_false_friend(text: str, start: int, term: str) -> bool:
    for friend in _FALSE_FRIENDS.get(term, ()):
        for found in re.finditer(rf"\b{re.escape(friend)}", text):
            if found.start() <= start < found.end():
                return True
    return False


def _normalize(value: str) -> str:
    return " ".join(_WORD.findall(value.lower()))


def _singular_phrase(phrase: str) -> str:
    words = phrase.split()
    if not words:
        return ""
    last = words[-1]
    if last.endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif last.endswith(("shes", "ches", "sses", "xes")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith("ss") and len(last) > 3:
        last = last[:-1]
    return " ".join([*words[:-1], last])


def _plural(word: str) -> str:
    return word + "s"
