from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cookfully.domain.food_semantics import FoodSemanticProfile

aliases = {
    "scallion": "green onion",
    "garbanzo": "chickpea",
    "caster sugar": "sugar",
    "confectioners sugar": "powdered sugar",
    "bell pepper": "sweet pepper",
    "super firm tofu": "extra firm tofu",
}


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()
    return aliases.get(normalized, normalized)


def rank_query(value: str) -> str:
    normalized = normalize(value)
    return " ".join(token for token in normalized.split() if not token[:1].isdigit())


def tokenize(value: str) -> list[str]:
    return [singularize(token) for token in normalize(value).split() if token]


def singularize(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and len(word) > 3 and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def semantic_query(concept: FoodSemanticProfile) -> str:
    values = [concept.canonical_identity, concept.part, concept.form]
    return " ".join(value for value in values if value and value != "whole_food")
