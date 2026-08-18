from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class Compatibility(StrEnum):
    COMPATIBLE = "compatible"
    REVIEW = "review"
    CONTRADICTORY = "contradictory"


@dataclass(frozen=True, slots=True)
class FoodSemanticProfile:
    canonical_identity: str | None
    category: str | None
    part: str | None
    state: str | None
    preparation: str | None
    form: str | None
    dietary_flags: frozenset[str]


@dataclass(frozen=True, slots=True)
class IngredientConcept(FoodSemanticProfile):
    quantity_text: str | None = None
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    compatibility: Compatibility
    reasons: tuple[str, ...]


_QUANTITY_RE = re.compile(
    r"\b\d+(?:\s+\d+)?(?:[./]\d+)?\s*(?:g|kg|mg|ml|l|oz|lb|lbs|cups?|tb?sp|tsp)\b",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")

_IDENTITY_ALIASES = {
    "garbanzo": "chickpea",
    "scallion": "onion",
    "spring onion": "onion",
    "caster sugar": "sugar",
    "confectioners sugar": "sugar",
    "bell pepper": "pepper",
    "super firm tofu": "tofu",
}
_CATEGORY_BY_IDENTITY = {
    "chicken": "poultry",
    "turkey": "poultry",
    "beef": "red_meat",
    "pork": "red_meat",
    "fish": "seafood",
    "salmon": "seafood",
    "shrimp": "seafood",
    "tofu": "soy_food",
    "tempeh": "soy_food",
    "seitan": "wheat_food",
    "lemon": "fruit",
    "lemongrass": "herb",
    "onion": "vegetable",
    "garlic": "vegetable",
    "paprika": "spice",
    "cayenne": "spice",
    "pepper": "spice",
    "salt": "seasoning",
    "sugar": "sweetener",
    "flour": "grain_product",
    "rice": "grain",
    "oat": "grain",
    "milk": "dairy",
    "buttermilk": "dairy",
    "cream": "dairy",
    "butter": "dairy",
    "oil": "oil",
    "water": "beverage",
    "vegetable": "vegetable",
    "yogurt": "dairy",
    "banana": "fruit",
    "apple": "fruit",
    "tomato": "vegetable",
    "potato": "vegetable",
    "chickpea": "legume",
    "lentil": "legume",
    "cashew": "nut",
    "almond": "nut",
    "flaxseed": "seed",
    "mustard": "condiment",
    "ketchup": "condiment",
    "vinegar": "condiment",
    "sauce": "condiment",
    "cornstarch": "grain_product",
}
_PARTS = ("breast", "thigh", "wing", "leg", "drumstick", "leaf", "root", "stem")
_STATES = ("raw", "cooked", "roasted", "fried", "dried", "frozen", "canned")
_PREPARATIONS = ("tandoori", "smoked", "grilled", "baked", "roasted", "pickled")
_FORMS = (
    ("meatless", "meat_substitute"),
    ("plant based", "meat_substitute"),
    ("powder", "powder"),
    ("sauce", "sauce"),
    ("broth", "broth"),
    ("paste", "paste"),
    ("juice", "juice"),
    ("flour", "flour"),
)


def profile_from_text(value: str) -> IngredientConcept:
    quantity_match = _QUANTITY_RE.search(value)
    quantity_text = quantity_match.group(0) if quantity_match else None
    text = _normalize(value)
    if quantity_match:
        text = _normalize(value[: quantity_match.start()] + value[quantity_match.end() :])

    alternatives = tuple(
        _normalize(item) for item in re.split(r"\s+or\s+|\s*;\s*", text) if _normalize(item)
    )
    identity = _identity(text)
    category = _CATEGORY_BY_IDENTITY.get(identity or "")
    if "vegan" in text or "plant based" in text:
        category = "plant_based_meat" if identity in {"chicken", "beef", "turkey"} else category
    part = next((item for item in _PARTS if re.search(rf"\b{item}s?\b", text)), None)
    state = next((item for item in _STATES if re.search(rf"\b{item}\b", text)), None)
    preparation = next((item for item in _PREPARATIONS if item in text), None)
    form = next((form for marker, form in _FORMS if marker in text), None)
    dietary_flags = frozenset(
        flag for flag in ("vegan", "vegetarian", "unsweetened", "gluten_free") if flag in text
    )
    return IngredientConcept(
        canonical_identity=identity,
        category=category,
        part=part,
        state=state,
        preparation=preparation,
        form=form or ("whole_food" if identity else None),
        dietary_flags=dietary_flags,
        quantity_text=quantity_text,
        alternatives=alternatives if len(alternatives) > 1 else (),
    )


def concept_signature(concept: IngredientConcept) -> str:
    payload = {
        "identity": concept.canonical_identity,
        "category": concept.category,
        "part": concept.part,
        "state": concept.state,
        "preparation": concept.preparation,
        "form": concept.form,
        "dietary": sorted(concept.dietary_flags),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compare_compatibility(
    query: FoodSemanticProfile, candidate: FoodSemanticProfile
) -> CompatibilityResult:
    reasons: list[str] = []
    hard_conflict = False
    review = False

    if query.canonical_identity and candidate.canonical_identity:
        if query.canonical_identity != candidate.canonical_identity:
            hard_conflict = True
            reasons.append("identity_conflict")

    if query.category and candidate.category and query.category != candidate.category:
        hard_conflict = True
        reasons.append("category_conflict")

    if query.part and candidate.part and query.part != candidate.part:
        hard_conflict = True
        reasons.append("part_conflict")
    elif query.part is None and candidate.part is not None:
        review = True
        reasons.append("candidate_part_unspecified")

    if query.state and candidate.state and query.state != candidate.state:
        hard_conflict = True
        reasons.append("state_conflict")
    if query.form and candidate.form and query.form != candidate.form:
        hard_conflict = True
        reasons.append("form_conflict")
    elif query.form is None and candidate.form not in {None, "whole_food"}:
        review = True
        reasons.append("candidate_form_unspecified")

    if query.preparation and candidate.preparation is None:
        review = True
        reasons.append("preparation_not_represented")
    elif query.preparation and candidate.preparation and query.preparation != candidate.preparation:
        review = True
        reasons.append("preparation_variant")

    if query.dietary_flags - candidate.dietary_flags:
        review = True
        reasons.append("dietary_attribute_not_represented")

    if hard_conflict:
        return CompatibilityResult(Compatibility.CONTRADICTORY, tuple(reasons))
    if review:
        return CompatibilityResult(Compatibility.REVIEW, tuple(reasons))
    return CompatibilityResult(Compatibility.COMPATIBLE, tuple(reasons))


def _normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(_TOKEN_RE.findall(ascii_value.casefold()))


def _identity(text: str) -> str | None:
    for alias, canonical in sorted(_IDENTITY_ALIASES.items(), key=lambda item: -len(item[0])):
        if alias in text:
            return canonical
    tokens = text.split()
    for identity in sorted(_CATEGORY_BY_IDENTITY, key=len, reverse=True):
        if identity in tokens or f"{identity}s" in tokens:
            return identity
    return tokens[-1].removesuffix("s") if tokens else None
