def test_quantities_module_importable() -> None:
    from cookfully.domain.ingredient_nutrition.quantities import (
        canonical_pantry_unit,
        convert_quantity,
        to_grams,
    )

    assert callable(to_grams)
    assert callable(convert_quantity)
    assert callable(canonical_pantry_unit)
