from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from importlib.metadata import version
from typing import Any

from ingredient_parser import parse_ingredient

from cookfully.domain.common import NUTRIENT_SCALE, quantize_decimal


@dataclass(frozen=True, slots=True)
class ParsedIngredientValue:
    original_text: str
    quantity_min: Decimal | None
    quantity_max: Decimal | None
    unit_code: str | None
    food_name: str | None
    preparation: str | None
    comment: str | None
    purpose: str | None
    optional: bool
    confidence: Decimal | None
    parser_name: str
    parser_version: str


def parse_ingredient_line(line: str) -> ParsedIngredientValue:
    parsed: Any = parse_ingredient(line, string_units=True, foundation_foods=False)
    amount: Any | None = parsed.amount[0] if parsed.amount else None
    if amount is not None and hasattr(amount, "amounts"):
        amount = amount.amounts[0] if amount.amounts else None
    names = [item.text for item in parsed.name]
    confidences = [Decimal(str(item.confidence)) for item in parsed.name]
    if amount is not None:
        confidences.append(Decimal(str(amount.confidence)))
    return ParsedIngredientValue(
        original_text=line,
        quantity_min=_decimal_quantity(amount.quantity) if amount is not None else None,
        quantity_max=_decimal_quantity(amount.quantity_max) if amount is not None else None,
        unit_code=_normalize_unit(str(amount.unit)) if amount is not None else None,
        food_name="; ".join(names) or None,
        preparation=parsed.preparation.text if parsed.preparation else None,
        comment=parsed.comment.text if parsed.comment else None,
        purpose=parsed.purpose.text if parsed.purpose else None,
        optional="optional" in line.casefold(),
        confidence=quantize_decimal(min(confidences), NUTRIENT_SCALE) if confidences else None,
        parser_name="ingredient-parser-nlp",
        parser_version=version("ingredient-parser-nlp"),
    )


def _decimal_quantity(value: Fraction | str) -> Decimal | None:
    if isinstance(value, Fraction):
        return quantize_decimal(
            Decimal(value.numerator) / Decimal(value.denominator), NUTRIENT_SCALE
        )
    try:
        return quantize_decimal(Decimal(value), NUTRIENT_SCALE)
    except Exception:
        return None


def _normalize_unit(value: str) -> str | None:
    normalized = value.strip().casefold().replace(" ", "_")
    aliases = {
        "g": "gram",
        "gram": "gram",
        "grams": "gram",
        "kg": "kilogram",
        "ml": "milliliter",
        "l": "liter",
        "oz": "ounce",
        "lb": "pound",
        "cup": "cup",
        "cups": "cup",
        "tablespoon": "tablespoon",
        "tablespoons": "tablespoon",
        "tbsp": "tablespoon",
        "tbsps": "tablespoon",
        "teaspoon": "teaspoon",
        "teaspoons": "teaspoon",
        "tsp": "teaspoon",
        "tsps": "teaspoon",
    }
    return aliases.get(normalized, normalized or None)
