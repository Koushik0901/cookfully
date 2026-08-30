"""Shared import representations used by web and cookbook decoders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ImportedRecipe:
    title: str
    source_url: str
    canonical_url: str
    image_url: str | None
    yield_quantity: Decimal | None
    yield_text: str | None
    ingredients: tuple[str, ...]
    ingredient_sections: tuple[int | None, ...]
    sections: tuple[str, ...]
    instructions: tuple[str, ...]
    source_nutrition: dict[str, str]
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    image_candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportedCookbook:
    title: str
    source_url: str
    canonical_url: str
    recipes: tuple[ImportedRecipe, ...]
