from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import (
    NUTRIENT_SCALE,
    SERVING_SCALE,
    DomainError,
    quantize_decimal,
    utc_now,
)
from cookfully.domain.units import IngredientMeasure, to_grams
from cookfully.domain.volume_assumptions import density_for
from cookfully.infrastructure.models.nutrition import IngredientMatch, NutritionCorrection
from cookfully.infrastructure.models.recipes import Ingredient, Recipe
from cookfully.infrastructure.models.reference_foods import FoodReference
from cookfully.infrastructure.repositories.nutrition import NutritionRepository

DECIMAL_FIELDS = frozenset(
    {
        "quantity_min",
        "quantity_max",
        "grams",
        "yield_quantity",
        "calories_kcal",
        "protein_g",
        "carbohydrate_g",
        "fat_g",
        "dietary_fiber_g",
        "sodium_mg",
        "potassium_mg",
        "calcium_mg",
        "iron_mg",
        "magnesium_mg",
        "vitamin_c_mg",
        "vitamin_d_ug",
        "vitamin_b12_ug",
    }
)
TEXT_FIELDS = frozenset({"unit", "food_name"})
REFERENCE_FIELDS = frozenset({"food_reference"})


class CorrectionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def activate(
        self,
        *,
        recipe_id: UUID,
        ingredient_id: UUID | None,
        field: str,
        created_by: UUID,
        decimal_value: Decimal | None = None,
        text_value: str | None = None,
        reference_id_value: UUID | None = None,
        reason: str | None = None,
    ) -> NutritionCorrection:
        typed_count = sum(
            value is not None for value in (decimal_value, text_value, reference_id_value)
        )
        if typed_count != 1:
            raise DomainError(
                "correction_value_invalid", "Provide exactly one correction value.", 422
            )
        if field in DECIMAL_FIELDS and decimal_value is not None:
            scale = SERVING_SCALE if field == "yield_quantity" else NUTRIENT_SCALE
            decimal_value = quantize_decimal(decimal_value, scale)
            if decimal_value < 0 or (field == "yield_quantity" and decimal_value == 0):
                raise DomainError(
                    "correction_value_invalid", "Correction value is out of range.", 422
                )
        elif field in TEXT_FIELDS and text_value is not None:
            text_value = text_value.strip()
            if not text_value:
                raise DomainError(
                    "correction_value_invalid", "Correction text cannot be empty.", 422
                )
        elif field in REFERENCE_FIELDS and reference_id_value is not None:
            pass
        else:
            raise DomainError(
                "correction_field_invalid", "Correction field and value do not match.", 422
            )
        with self._session_factory.begin() as session:
            recipe = session.get(Recipe, recipe_id, with_for_update=True)
            if recipe is None:
                raise DomainError("recipe_not_found", "Recipe was not found.", 404)
            if recipe.status == "archived":
                raise DomainError(
                    "recipe_archived", "Restore the recipe before correcting it.", 409
                )
            if ingredient_id is not None:
                ingredient = session.get(Ingredient, ingredient_id)
                if ingredient is None or ingredient.recipe_id != recipe_id:
                    raise DomainError(
                        "ingredient_not_found", "Recipe ingredient was not found.", 404
                    )
            if (
                reference_id_value is not None
                and session.get(FoodReference, reference_id_value) is None
            ):
                raise DomainError("food_reference_not_found", "Food reference was not found.", 404)
            repository = NutritionRepository(session)
            correction = repository.activate_correction(
                NutritionCorrection(
                    recipe_id=recipe_id,
                    ingredient_id=ingredient_id,
                    field=field,
                    decimal_value=decimal_value,
                    text_value=text_value,
                    reference_id_value=reference_id_value,
                    reason=reason,
                    active=True,
                    created_by=created_by,
                )
            )
            if field == "food_reference" and ingredient is not None:
                assert reference_id_value is not None
                food = session.get(FoodReference, reference_id_value)
                assert food is not None
                grams_min: Decimal | None = None
                grams_max: Decimal | None = None
                conversion_method: str | None = None
                assumption: str | None = None
                try:
                    converted = to_grams(
                        IngredientMeasure(
                            ingredient.quantity_min,
                            ingredient.quantity_max,
                            ingredient.unit_code,
                            ingredient.optional,
                        ),
                        density_g_per_ml=density_for(food.description),
                    )
                    grams_min = converted.minimum
                    grams_max = converted.maximum
                    conversion_method = converted.method
                    assumption = converted.assumption
                except DomainError:
                    pass
                repository.activate_match(
                    IngredientMatch(
                        ingredient_id=ingredient.id,
                        food_reference_id=food.id,
                        status="manual",
                        match_method="manual",
                        match_score=None,
                        grams_min=grams_min,
                        grams_max=grams_max,
                        conversion_method=conversion_method,
                        assumption_text=assumption,
                        source_release_id=food.dataset.release_id,
                        input_hash=recipe.input_hash,
                        active=True,
                    )
                )
            recipe.version += 1
            return correction

    def reset(
        self,
        correction_id: UUID,
        *,
        recipe_id: UUID | None = None,
        now: datetime | None = None,
    ) -> NutritionCorrection:
        with self._session_factory.begin() as session:
            correction = session.scalar(
                select(NutritionCorrection)
                .where(NutritionCorrection.id == correction_id)
                .with_for_update()
            )
            if correction is None:
                raise DomainError("correction_not_found", "Correction was not found.", 404)
            if recipe_id is not None and correction.recipe_id != recipe_id:
                raise DomainError("correction_not_found", "Correction was not found.", 404)
            correction.active = False
            correction.reset_at = now or utc_now()
            recipe = session.get(Recipe, correction.recipe_id, with_for_update=True)
            if recipe is not None:
                recipe.version += 1
            return correction
