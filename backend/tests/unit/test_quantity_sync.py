def test_quantities_module_importable() -> None:
    from cookfully.domain.ingredient_nutrition.quantities import (
        canonical_pantry_unit,
        convert_quantity,
        to_grams,
    )

    assert callable(to_grams)
    assert callable(convert_quantity)
    assert callable(canonical_pantry_unit)


def test_engine_convert_and_pantry_wrapper_parity():
    from decimal import Decimal

    from cookfully.application.ingredient_engine import engine
    from cookfully.application.pantry import canonical_pantry_unit as pantry_canonical
    from cookfully.application.pantry import convert_quantity as pantry_convert

    assert engine.convert_quantity(Decimal("1"), "tbsp", "ml") == Decimal("15.000000")
    assert pantry_convert(Decimal("1000"), "mg", "g") == Decimal("1.000000")
    assert pantry_canonical("Grams.") == "g"
    # pantry wrapper must still raise pantry codes, not domain codes
    import pytest

    from cookfully.domain.common import DomainError

    with pytest.raises(DomainError) as exc:
        pantry_convert(Decimal("1"), "g", "ml")
    assert exc.value.code == "pantry_unit_incompatible"


def test_owner_serving_through_engine():
    from decimal import Decimal

    from cookfully.application.ingredient_engine import engine
    from cookfully.domain.ingredient_nutrition.quantities import IngredientMeasure

    class FakeFood:
        display_name = "Test Scoops"
        typical_serving_g = Decimal("30")
        typical_serving_unit = "scoop"

    m = IngredientMeasure(Decimal("2"), None, "scoop")
    r = engine.to_grams(m, owner_food=FakeFood())
    assert r.method == "owner_serving"
    assert r.minimum == Decimal("60.000000")
    # casefold
    m2 = IngredientMeasure(Decimal("1"), None, "SCOOP")
    assert engine.to_grams(m2, owner_food=FakeFood()).method == "owner_serving"
    # non-matching falls through to Pint error, not owner_serving
    import pytest

    from cookfully.domain.common import DomainError

    with pytest.raises(DomainError):
        engine.to_grams(IngredientMeasure(Decimal("1"), None, "cup"), owner_food=FakeFood())


def test_convert_new_aliases():
    from decimal import Decimal

    from cookfully.application.ingredient_engine import engine

    assert engine.convert_quantity(Decimal("2"), "cup", "ml") == Decimal("480.000000")
    assert engine.convert_quantity(Decimal("1"), "oz", "g") == Decimal("28.349523")
    # quantized to 6dp via NUTRIENT_SCALE
    assert engine.convert_quantity(Decimal("1"), "lb", "g") == Decimal("453.592370")


def test_boundary_only_quantities_and_engine_import_pint():
    import pathlib

    root = pathlib.Path("backend/src/cookfully")
    # also try absolute fallback for different cwd
    if not root.exists():
        root = pathlib.Path(__file__).resolve().parents[2] / "src" / "cookfully"
    offenders = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        if "import pint" in text or "from pint" in text:
            rel = str(p.relative_to(root)).replace("\\", "/")
            if rel not in (
                "domain/ingredient_nutrition/quantities.py",
                "application/ingredient_engine.py",
            ):
                offenders.append(rel)
    assert offenders == [], f"unexpected pint imports: {offenders}"
