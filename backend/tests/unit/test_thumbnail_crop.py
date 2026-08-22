from decimal import Decimal

import pytest

from cookfully.domain.recipes import ThumbnailCrop


def test_default_is_full_image() -> None:
    crop = ThumbnailCrop()
    assert crop.x == Decimal("0")
    assert crop.y == Decimal("0")
    assert crop.width == Decimal("1")
    assert crop.height == Decimal("1")


def test_valid_partial_rect_accepted() -> None:
    crop = ThumbnailCrop(Decimal("0.25"), Decimal("0.125"), Decimal("0.5"), Decimal("0.375"))
    assert crop.width == Decimal("0.5")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"x": Decimal("-0.1")},
        {"y": Decimal("1.1")},
        {"width": Decimal("0")},
        {"width": Decimal("1.2")},
        {"height": Decimal("0")},
        {"x": Decimal("0.75"), "width": Decimal("0.5")},
        {"y": Decimal("0.75"), "height": Decimal("0.5")},
    ],
)
def test_invalid_values_rejected(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        ThumbnailCrop(**kwargs)
