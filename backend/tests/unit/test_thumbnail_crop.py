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
    ("kwargs", "message"),
    [
        ({"x": Decimal("-0.1")}, "x must be between 0 and 1"),
        ({"y": Decimal("1.1")}, "y must be between 0 and 1"),
        ({"width": Decimal("0")}, "width must be between 0 and 1"),
        ({"width": Decimal("1.2")}, "width must be between 0 and 1"),
        ({"height": Decimal("0")}, "height must be between 0 and 1"),
        ({"x": Decimal("0.75"), "width": Decimal("0.5")}, "past the right edge"),
        ({"y": Decimal("0.75"), "height": Decimal("0.5")}, "past the bottom edge"),
    ],
)
def test_invalid_values_rejected(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ThumbnailCrop(**kwargs)
