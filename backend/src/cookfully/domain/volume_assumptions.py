from __future__ import annotations

import re
from decimal import Decimal

from cookfully.domain.common import NUTRIENT_SCALE, quantize_decimal

DEFAULT_VOLUME_DENSITY_G_PER_ML = Decimal("0.700000")
COOKED_RICE_DENSITY_G_PER_ML = Decimal("0.810000")
RAW_RICE_DENSITY_G_PER_ML = Decimal("0.780000")

_DENSE_CLASSES: tuple[tuple[tuple[str, ...], Decimal], ...] = (
    (("honey", "syrup", "molasses", "agave", "maple", "treacle"), Decimal("1.400000")),
    (("oil",), Decimal("0.910000")),
    (
        ("milk", "yogurt", "cream", "buttermilk", "kefir", "cottage", "ricotta"),
        Decimal("1.030000"),
    ),
    (("flour",), Decimal("0.530000")),
    (
        ("spice", "powder", "ground", "seasoning", "curry", "paprika", "cinnamon"),
        Decimal("0.550000"),
    ),
    (("oats", "oatmeal", "muesli"), Decimal("0.340000")),
)

_NUT_BUTTER_KERNELS = ("peanut", "almond", "cashew", "hazelnut", "walnut")
_NUT_BUTTER_DENSITY_G_PER_ML = Decimal("0.960000")


def density_for(food_name: str) -> Decimal | None:
    """Class-keyword volume density assumption for a food description.

    Returns None for a blank name so a failed parse never invents a density.
    Unclassified foods fall back to the produce/liquids default.
    """
    tokens = re.sub(r"[^a-z0-9]+", " ", " ".join(food_name.split()).casefold()).split()
    if not tokens:
        return None
    token_set = set(tokens)
    if "cooked" in token_set and "rice" in token_set:
        return COOKED_RICE_DENSITY_G_PER_ML
    if "rice" in token_set:
        return RAW_RICE_DENSITY_G_PER_ML
    if any(token in token_set for token in _NUT_BUTTER_KERNELS) and "butter" in token_set:
        return _NUT_BUTTER_DENSITY_G_PER_ML
    for keywords, density in _DENSE_CLASSES:
        if any(any(token.startswith(keyword) for token in token_set) for keyword in keywords):
            return density
    return quantize_decimal(DEFAULT_VOLUME_DENSITY_G_PER_ML, NUTRIENT_SCALE)
