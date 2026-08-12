from __future__ import annotations

from decimal import Decimal

from cookfully.application.pantry_search import (
    PantrySearchIngredient,
    PantrySearchItem,
    PantrySearchRecipe,
    rank_makeable_recipes,
)


def test_fully_then_partially_makeable_recipes_are_ranked_with_missing_items() -> None:
    pantry = (
        PantrySearchItem("chicken breast", Decimal("500.000000"), "g", "matched"),
        PantrySearchItem("rice", Decimal("0.250000"), "kg", "manual"),
        PantrySearchItem("salt", Decimal("1.000000"), "g", "proposed"),
    )
    recipes = (
        PantrySearchRecipe(
            "full",
            "Chicken rice",
            (
                PantrySearchIngredient(
                    "chicken breast", "400 g chicken breast", Decimal("400"), "g"
                ),
                PantrySearchIngredient("rice", "200 g rice", Decimal("200"), "g"),
            ),
        ),
        PantrySearchRecipe(
            "partial",
            "Chicken salad",
            (
                PantrySearchIngredient(
                    "chicken breast", "300 g chicken breast", Decimal("300"), "g"
                ),
                PantrySearchIngredient("lettuce", "1 lettuce", Decimal("1"), "count"),
            ),
        ),
        PantrySearchRecipe(
            "none",
            "Salt potatoes",
            (
                PantrySearchIngredient("salt", "1 g salt", Decimal("1"), "g"),
                PantrySearchIngredient("potato", "500 g potatoes", Decimal("500"), "g"),
            ),
        ),
    )

    result = rank_makeable_recipes(recipes, pantry)

    assert [item.recipe_id for item in result] == ["full", "partial", "none"]
    assert result[0].makeability == "full"
    assert result[0].coverage_ratio == Decimal("1.000000")
    assert result[0].missing_ingredients == ()
    assert result[1].makeability == "partial"
    assert result[1].coverage_ratio == Decimal("0.500000")
    assert result[1].missing_ingredients == ("1 lettuce",)
    # Proposed/ambiguous inventory is intentionally unavailable for automatic matching.
    assert result[2].makeability == "none"
    assert result[2].missing_ingredients == ("1 g salt", "500 g potatoes")


def test_unknown_quantities_and_incompatible_units_remain_explicitly_missing() -> None:
    result = rank_makeable_recipes(
        (
            PantrySearchRecipe(
                "soup",
                "Soup",
                (
                    PantrySearchIngredient("stock", "stock to taste", None, None),
                    PantrySearchIngredient("water", "250 ml water", Decimal("250"), "ml"),
                ),
            ),
        ),
        (PantrySearchItem("water", Decimal("250"), "g", "matched"),),
    )
    assert result[0].makeability == "none"
    assert result[0].coverage_ratio == Decimal("0.000000")
    assert result[0].missing_ingredients == ("stock to taste", "250 ml water")
