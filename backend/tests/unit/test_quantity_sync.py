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
