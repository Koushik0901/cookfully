from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from vigor_vine.domain.grocery import GroceryIngredient, aggregate_grocery_ingredients

ENTRY_A = UUID("00000000-0000-4000-8000-000000000001")
ENTRY_B = UUID("00000000-0000-4000-8000-000000000002")
INGREDIENT_A = UUID("00000000-0000-4000-8000-000000000011")
INGREDIENT_B = UUID("00000000-0000-4000-8000-000000000012")


def ingredient(
    *,
    entry_id: UUID = ENTRY_A,
    ingredient_id: UUID = INGREDIENT_A,
    food_name: str = "red onion",
    quantity: Decimal | None = Decimal("1"),
    unit_code: str | None = "g",
    unit_text: str | None = "g",
    planned_servings: Decimal = Decimal("1"),
    recipe_yield: Decimal = Decimal("1"),
    original_text: str = "1 g red onion",
) -> GroceryIngredient:
    return GroceryIngredient(
        meal_plan_entry_id=entry_id,
        ingredient_id=ingredient_id,
        original_text=original_text,
        food_name=food_name,
        quantity=quantity,
        unit_code=unit_code,
        unit_text=unit_text,
        planned_servings=planned_servings,
        recipe_yield=recipe_yield,
    )


@given(
    quantity=st.decimals(min_value="0", max_value="10000", places=6, allow_nan=False),
    servings=st.decimals(min_value="0.001", max_value="100", places=3, allow_nan=False),
    recipe_yield=st.decimals(min_value="0.001", max_value="100", places=3, allow_nan=False),
)
def test_serving_scaling_is_six_decimal_and_rounds_half_up(
    quantity: Decimal, servings: Decimal, recipe_yield: Decimal
) -> None:
    result = aggregate_grocery_ingredients(
        [
            ingredient(
                quantity=quantity,
                planned_servings=servings,
                recipe_yield=recipe_yield,
            )
        ]
    )[0]
    expected = (quantity * servings / recipe_yield).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    assert result.quantity == expected
    assert result.sources[0].quantity_contribution == expected
    assert result.quantity.as_tuple().exponent == -6


def test_normalized_identity_and_compatible_units_aggregate_with_traceability() -> None:
    result = aggregate_grocery_ingredients(
        [
            ingredient(food_name=" Red Onions ", quantity=Decimal("0.500000"), unit_code="kg"),
            ingredient(
                entry_id=ENTRY_B,
                ingredient_id=INGREDIENT_B,
                food_name="red-onion",
                quantity=Decimal("250.000000"),
                unit_code="g",
                original_text="250 g red onion",
            ),
        ]
    )
    assert len(result) == 1
    assert result[0].normalized_food_name == "red onion"
    assert result[0].aggregation_key == "red onion|mass:g"
    assert result[0].quantity == Decimal("750.000000")
    assert result[0].unit_code == "g"
    assert [source.quantity_contribution for source in result[0].sources] == [
        Decimal("500.000000"),
        Decimal("250.000000"),
    ]
    assert {source.meal_plan_entry_id for source in result[0].sources} == {ENTRY_A, ENTRY_B}


def test_incompatible_and_unquantified_items_stay_separate_and_are_reviewable() -> None:
    result = aggregate_grocery_ingredients(
        [
            ingredient(quantity=Decimal("2"), unit_code="tsp", unit_text="tsp"),
            ingredient(
                entry_id=ENTRY_B,
                ingredient_id=INGREDIENT_B,
                quantity=Decimal("5"),
                unit_code="g",
                unit_text="g",
            ),
            ingredient(
                entry_id=UUID("00000000-0000-4000-8000-000000000003"),
                ingredient_id=UUID("00000000-0000-4000-8000-000000000013"),
                quantity=None,
                unit_code=None,
                unit_text=None,
                original_text="red onion to taste",
            ),
        ]
    )
    assert len(result) == 3
    assert all(item.needs_review for item in result)
    assert {item.unit_code for item in result} == {"ml", "g", None}
    assert next(item for item in result if item.quantity is None).sources[0].original_text == (
        "red onion to taste"
    )
