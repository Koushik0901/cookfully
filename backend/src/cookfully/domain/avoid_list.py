"""Which recipe ingredients contain something on the owner's avoid list, by their own words.

Deterministic and conservative: an avoided item matches an ingredient line when one of its words (or
a known member of a group such as "shellfish" or "tree nuts") appears in the line, allowing simple
plurals. Hidden ingredients (anchovy in Worcestershire sauce) are left to the model-based check,
which only ever adds warnings to these.

Pure: no I/O.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
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
        "crawfish",
        "krill",
        "cockle",
        "abalone",
        "whelk",
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
        "bonito",
        "katsuobushi",
        "herring",
        "swordfish",
        "mahi",
        "catfish",
        "perch",
        "sole",
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
        "chestnut",
        "marzipan",
        "nutella",
        "praline",
        "amaretto",
        "frangipane",
        "gianduja",
        "orgeat",
        "mixed nut",
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
        "chestnut",
        "marzipan",
        "nutella",
        "praline",
        "amaretto",
        "frangipane",
        "gianduja",
        "orgeat",
        "mixed nut",
        "groundnut",
        "arachis",
        "satay",
    ),
    "peanut": ("peanut", "groundnut", "arachis", "satay", "mixed nut"),
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
        "mascarpone",
        "paneer",
        "half and half",
        "creme fraiche",
        "halloumi",
        "kefir",
        "casein",
        "caseinate",
        "custard",
        "brie",
        "camembert",
        "gouda",
        "gruyere",
        "provolone",
        "gelato",
        "lactose",
        "eggnog",
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
        "wrap",
        "pita",
        "bagel",
        "bun",
        "naan",
        "cracker",
        "crouton",
        "tortilla",
        "bulgur",
        "farro",
        "spelt",
        "seitan",
        "orzo",
        "macaroni",
        "lasagna",
        "beer",
        "ale",
        "lager",
        "stout",
        "malt",
        "ramen",
        "pretzel",
        "kamut",
        "tempura",
        "udon",
    ),
    "egg": ("egg", "mayonnaise", "aioli", "meringue", "eggnog", "yolk", "albumen", "mayo"),
    "soy": ("soy", "soya", "soybean", "tofu", "edamame", "tempeh", "miso", "tamari"),
    "sesame": ("sesame", "tahini", "halva", "halvah", "benne", "gomasio", "hummus"),
    "pork": (
        "pork",
        "bacon",
        "ham",
        "prosciutto",
        "pancetta",
        "chorizo",
        "lard",
        "guanciale",
        "salami",
        "pepperoni",
        "mortadella",
    ),
    "beef": ("beef", "steak", "brisket", "veal"),
    "poultry": ("chicken", "turkey", "duck", "goose", "quail"),
    "meat": (
        "meat",
        "beef",
        "steak",
        "brisket",
        "veal",
        "pork",
        "bacon",
        "ham",
        "prosciutto",
        "pancetta",
        "chorizo",
        "salami",
        "pepperoni",
        "sausage",
        "lard",
        "guanciale",
        "lamb",
        "mutton",
        "goat",
        "venison",
        "chicken",
        "turkey",
        "duck",
        "goose",
        "quail",
        "gelatin",
    ),
    "honey": ("honey", "mead"),
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
    "noodle": ("rice noodle", "glass noodle", "zucchini noodle", "kelp noodle", "shirataki noodle"),
    "pasta": (
        "gluten free pasta",
        "rice pasta",
        "chickpea pasta",
        "lentil pasta",
        "zucchini pasta",
    ),
    "flour": (
        "almond flour",
        "rice flour",
        "coconut flour",
        "chickpea flour",
        "corn flour",
        "buckwheat flour",
        "tapioca flour",
        "potato flour",
        "gluten free flour",
        "oat flour",
    ),
    "bread": ("gluten free bread",),
    "tortilla": ("corn tortilla",),
    "wrap": ("lettuce wrap",),
    "ale": ("ginger ale",),
    "beer": ("root beer", "ginger beer"),
    "custard": ("custard apple",),
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

    terms = [(item, _terms(item), _free_forms(item)) for item in avoid if item.strip()]
    warnings: list[AvoidWarning] = []
    for line in lines:
        text = _normalize(line.text)
        for item, words, forms in terms:
            if any(_contains(text, word, forms) for word in words):
                warnings.append(AvoidWarning(line.ingredient_id, item))
    return tuple(warnings)


def _terms(item: str) -> tuple[str, ...]:
    phrase = _singular_phrase(_normalize(item))
    terms = {phrase}
    for group, members in GROUPS.items():
        if phrase in {group, _plural(group)} or phrase == _singular_phrase(group):
            terms.update(members)
    return tuple(sorted(terms))


def _free_forms(item: str) -> tuple[str, ...]:
    """Names a "<name> free" label can use for this avoid-list entry (the entry and its groups)."""

    phrase = _singular_phrase(_normalize(item))
    forms = {phrase} if phrase else set()
    for group in GROUPS:
        if phrase in {group, _plural(group)} or phrase == _singular_phrase(group):
            forms.add(group)
    return tuple(sorted(forms))


@lru_cache(maxsize=8192)
def _term_pattern(term: str) -> re.Pattern[str]:
    """Compiled once per term: building it on every check thrashed Python's small regex cache."""

    if term.endswith("y") and len(term) > 2:
        return re.compile(rf"\b{re.escape(term[:-1])}(?:y|ies)\b")
    return re.compile(rf"\b{re.escape(term)}(?:s|es)?\b")


@lru_cache(maxsize=8192)
def _friend_pattern(friend: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(friend)}")


def _contains(text: str, term: str, free_forms: Sequence[str] = ()) -> bool:
    if not term:
        return False
    for match in _term_pattern(term).finditer(text):
        if text.startswith(" free", match.end()):
            continue  # "gluten free", "dairy free" say the opposite
        if any(text[: match.start()].endswith(f"{form} free ") for form in free_forms):
            continue  # "dairy free cheese" is the free-from kind
        if not _is_false_friend(text, match.start(), term):
            return True
    return False


def _is_false_friend(text: str, start: int, term: str) -> bool:
    for friend in _FALSE_FRIENDS.get(term, ()):
        for found in _friend_pattern(friend).finditer(text):
            if found.start() <= start < found.end():
                return True
    return False


def _normalize(value: str) -> str:
    """Lowercase ASCII words only, after folding accents and compatibility forms.

    "Jalapeño", "jalapeno" and fullwidth or ligature spellings ("ﬁsh") all reduce to the same plain
    letters, so a match never depends on how a recipe site encoded the text.
    """

    folded = unicodedata.normalize("NFKD", value).casefold()
    plain = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(_WORD.findall(plain))


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
