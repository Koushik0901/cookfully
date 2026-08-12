from decimal import Decimal

from cookfully.domain.volume_assumptions import density_for


def test_density_for_returns_class_assumptions() -> None:
    assert density_for("honey") == Decimal("1.40")
    assert density_for("olive oil") == Decimal("0.91")
    assert density_for("whole milk") == Decimal("1.03")
    assert density_for("greek yogurt") == Decimal("1.03")
    assert density_for("rolled oats") == Decimal("0.34")
    assert density_for("wheat flour") == Decimal("0.53")


def test_density_for_distinguishes_cooked_rice_from_raw() -> None:
    assert density_for("cooked white rice") == Decimal("0.81")
    assert density_for("rice, white, long-grain, raw") == Decimal("0.78")


def test_density_for_defaults_to_produce_and_liquids() -> None:
    assert density_for("mixed vegetables") == Decimal("0.70")
    assert density_for("blueberries") == Decimal("0.70")
    assert density_for("soy sauce") == Decimal("0.70")


def test_density_for_blank_name_is_none() -> None:
    assert density_for("") is None
