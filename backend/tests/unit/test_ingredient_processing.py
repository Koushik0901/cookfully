from decimal import Decimal

import pytest

from vigor_vine.domain.common import DomainError
from vigor_vine.domain.units import IngredientMeasure, coverage_ratio, to_grams


def test_ranges_density_count_weights_and_unsafe_conversions() -> None:
    ranged = IngredientMeasure(Decimal("1"), Decimal("2"), "cup", optional=False)
    converted = to_grams(ranged, density_g_per_ml=Decimal("0.96"))
    assert converted.minimum == Decimal("230.400000")
    assert converted.maximum == Decimal("460.800000")

    counted = to_grams(IngredientMeasure(Decimal("2"), None, "item"), count_weight_g=Decimal("50"))
    assert counted.minimum == counted.maximum == Decimal("100.000000")
    with pytest.raises(DomainError, match="density"):
        to_grams(IngredientMeasure(Decimal("1"), None, "cup"))
    with pytest.raises(DomainError, match="range"):
        IngredientMeasure(Decimal("2"), Decimal("1"), "gram")


def test_lower_of_mass_and_required_count_coverage() -> None:
    ingredients = [
        IngredientMeasure(Decimal("100"), None, "gram", matched=True),
        IngredientMeasure(Decimal("100"), None, "gram", matched=False),
        IngredientMeasure(None, None, None, matched=False),
        IngredientMeasure(None, None, None, optional=True, matched=False),
    ]
    coverage = coverage_ratio(ingredients)
    assert coverage.mass == Decimal("0.500000")
    assert coverage.required_count == Decimal("0.333333")
    assert coverage.overall == Decimal("0.333333")
