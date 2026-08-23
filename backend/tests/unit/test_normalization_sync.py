import pytest

from cookfully.domain.ingredient_nutrition.normalization import normalize, singularize
from cookfully.infrastructure.repositories.nutrition import _token_variants


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Crème-Fraîche (Light)  ", "creme fraiche light"),
        ("Bananas, raw", "bananas raw"),
        ("berries", "berries"),
        ("super firm tofu", "extra firm tofu"),
        ("garbanzo", "chickpea"),
        ("  ", ""),
    ],
)
def test_normalize_parity(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "token",
    ["banana", "berries", "tomatoes", "glass", "crème", "super"],
)
def test_token_variants_mirrors_singularize(token: str) -> None:
    normalized = normalize(token)
    base = normalized.split()[0] if normalized else token
    expected = sorted({base, singularize(base), base + "s"})
    assert _token_variants(base) == expected
