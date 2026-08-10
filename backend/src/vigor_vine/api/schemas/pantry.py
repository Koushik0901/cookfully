from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from vigor_vine.api.schemas.recipes import ApiModel, Decimal6
from vigor_vine.application.pantry import PantryItemRead
from vigor_vine.application.pantry_deductions import PantryDeductionRead
from vigor_vine.application.pantry_search import PantryRecipeScore
from vigor_vine.domain.common import canonical_decimal


class PantryItemWriteRequest(ApiModel):
    display_name: str = Field(alias="displayName", min_length=1, max_length=240)
    quantity: Decimal6
    unit: str = Field(min_length=1, max_length=80)
    food_reference_id: UUID | None = Field(alias="foodReferenceId", default=None)


class PantryItemResponse(PantryItemWriteRequest):
    id: UUID
    normalized_food_name: str = Field(alias="normalizedFoodName")
    match_status: Literal["unmatched", "proposed", "matched", "manual"] = Field(alias="matchStatus")
    match_confidence: str | None = Field(alias="matchConfidence")
    version: int

    @classmethod
    def from_read(cls, value: PantryItemRead) -> PantryItemResponse:
        return cls(
            id=value.id,
            display_name=value.display_name,
            normalized_food_name=value.normalized_food_name,
            quantity=value.quantity,
            unit=value.unit,
            food_reference_id=value.food_reference_id,
            match_status=value.match_status,
            match_confidence=(
                canonical_decimal(value.match_confidence)
                if value.match_confidence is not None
                else None
            ),
            version=value.version,
        )


class PantryRecipeMatchResponse(ApiModel):
    recipe_id: UUID = Field(alias="recipeId")
    recipe_title: str = Field(alias="recipeTitle")
    availability: Literal["full", "partial", "none"]
    coverage_ratio: str = Field(alias="coverageRatio")
    missing_ingredients: tuple[str, ...] = Field(alias="missingIngredients")

    @classmethod
    def from_score(cls, value: PantryRecipeScore) -> PantryRecipeMatchResponse:
        return cls(
            recipe_id=UUID(value.recipe_id),
            recipe_title=value.title,
            availability=value.makeability,
            coverage_ratio=canonical_decimal(value.coverage_ratio),
            missing_ingredients=value.missing_ingredients,
        )


class PantryDeductionApplyRequest(ApiModel):
    expected_grocery_list_version: int = Field(alias="expectedGroceryListVersion", ge=1)
    grocery_item_ids: tuple[UUID, ...] | None = Field(alias="groceryItemIds", default=None)


class PantryDeductionResponse(ApiModel):
    id: UUID
    pantry_item_id: UUID = Field(alias="pantryItemId")
    grocery_item_id: UUID = Field(alias="groceryItemId")
    pantry_quantity: str = Field(alias="pantryQuantity")
    pantry_unit: str = Field(alias="pantryUnit")
    grocery_quantity: str = Field(alias="groceryQuantity")
    grocery_unit: str = Field(alias="groceryUnit")
    assumption: str
    status: Literal["applied", "reversed"]
    applied_at: datetime = Field(alias="appliedAt")
    reversed_at: datetime | None = Field(alias="reversedAt")
    version: int

    @classmethod
    def from_read(cls, value: PantryDeductionRead) -> PantryDeductionResponse:
        return cls(
            id=value.id,
            pantry_item_id=value.pantry_item_id,
            grocery_item_id=value.grocery_item_id,
            pantry_quantity=canonical_decimal(value.pantry_quantity),
            pantry_unit=value.pantry_unit,
            grocery_quantity=canonical_decimal(value.grocery_quantity),
            grocery_unit=value.grocery_unit,
            assumption=value.assumption,
            status=value.status,
            applied_at=value.applied_at,
            reversed_at=value.reversed_at,
            version=value.version,
        )
