"""Weight buckets for counted ingredients ("1 medium onion") that have no recorded weight.

The panel picks the bucket that holds the weight of ONE such item as written (size words
included). The answer is a probability spread over buckets, so the gram range is read off the
distribution (roughly its 10th and 90th percentiles) instead of trusting one guess: an unsure
panel produces a wide range, which the nutrition roll-up already carries as an estimate.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

# key -> (lower edge g, upper edge g, description the model reads)
COUNT_WEIGHT_BUCKETS: dict[str, tuple[Decimal, Decimal, str]] = {
    "under_8": (
        Decimal(1),
        Decimal(8),
        "Under 8 g: a garlic clove, an olive, a mint sprig, a sugar cube.",
    ),
    "8_to_20": (
        Decimal(8),
        Decimal(20),
        "8 to 20 g: a cherry tomato, a date, a small mushroom, a strawberry.",
    ),
    "20_to_45": (
        Decimal(20),
        Decimal(45),
        "20 to 45 g: a large egg yolk, a walnut half, a small plum, a slice of bacon.",
    ),
    "45_to_90": (
        Decimal(45),
        Decimal(90),
        "45 to 90 g: a large egg, a small onion, a plum tomato, a small potato, a lime.",
    ),
    "90_to_150": (
        Decimal(90),
        Decimal(150),
        "90 to 150 g: a medium onion, an apple, a medium tomato, a lemon, an orange.",
    ),
    "150_to_250": (
        Decimal(150),
        Decimal(250),
        "150 to 250 g: a large potato, a chicken breast, a large apple, a bell pepper.",
    ),
    "250_to_450": (
        Decimal(250),
        Decimal(450),
        "250 to 450 g: a large chicken breast, a whole cauliflower head, an eggplant.",
    ),
    "450_to_800": (
        Decimal(450),
        Decimal(800),
        "450 to 800 g: a small whole chicken, a head of cabbage, a large squash.",
    ),
    "800_to_1500": (
        Decimal(800),
        Decimal(1500),
        "800 g to 1.5 kg: a whole chicken, a large cabbage, a small watermelon.",
    ),
    "over_1500": (
        Decimal(1500),
        Decimal(3000),
        "Over 1.5 kg: a whole turkey, a large watermelon, a whole fish or roast.",
    ),
}

LOW_PERCENTILE = Decimal("0.1")
HIGH_PERCENTILE = Decimal("0.9")
ORDER = tuple(COUNT_WEIGHT_BUCKETS)


def weight_range(probabilities: Mapping[str, Decimal]) -> tuple[Decimal, Decimal] | None:
    """Gram range (about p10 to p90) of one item, or ``None`` when there is no usable spread."""

    weights = [max(probabilities.get(key, Decimal(0)), Decimal(0)) for key in ORDER]
    total = sum(weights, Decimal(0))
    if total <= 0:
        return None
    low: Decimal | None = None
    high: Decimal | None = None
    cumulative = Decimal(0)
    for key, weight in zip(ORDER, weights, strict=True):
        cumulative += weight / total
        lower, upper, _ = COUNT_WEIGHT_BUCKETS[key]
        if low is None and cumulative >= LOW_PERCENTILE:
            low = lower
        if cumulative >= HIGH_PERCENTILE:
            high = upper
            break
    if low is None or high is None:
        return None
    return low, high
