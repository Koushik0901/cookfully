from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cookfully.domain.common import MAX_VERSION

# The columns are NUMERIC(20, 6), so anything past 14 integer digits cannot be stored; a nutrition
# label or serving never needs more than a hundred million of any unit.
MAX_FOOD_AMOUNT = Decimal("100000000")


class OwnerFoodWriteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    display_name: Annotated[str, Field(alias="displayName", min_length=1, max_length=500)]
    brand: Annotated[str | None, Field(max_length=240)] = None
    calories_kcal: Annotated[Decimal, Field(alias="caloriesKcal", ge=0, le=MAX_FOOD_AMOUNT)]
    protein_g: Annotated[Decimal, Field(alias="proteinG", ge=0, le=MAX_FOOD_AMOUNT)]
    carbohydrate_g: Annotated[Decimal, Field(alias="carbohydrateG", ge=0, le=MAX_FOOD_AMOUNT)]
    fat_g: Annotated[Decimal, Field(alias="fatG", ge=0, le=MAX_FOOD_AMOUNT)]
    basis_grams: Annotated[
        Decimal, Field(alias="basisGrams", ge=1, le=MAX_FOOD_AMOUNT, default=Decimal("100.000"))
    ]
    typical_serving_g: Annotated[
        Decimal | None, Field(alias="typicalServingG", gt=0, le=MAX_FOOD_AMOUNT, default=None)
    ]
    typical_serving_unit: Annotated[
        str | None, Field(alias="typicalServingUnit", max_length=20, default=None)
    ]


class OwnerFoodUpdateRequest(OwnerFoodWriteRequest):
    expected_version: Annotated[int, Field(alias="expectedVersion", ge=1, le=MAX_VERSION)]


class OwnerFoodResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: UUID
    display_name: Annotated[str, Field(alias="displayName")]
    normalized_name: Annotated[str, Field(alias="normalizedName")]
    brand: str | None = None
    calories_kcal: Annotated[Decimal, Field(alias="caloriesKcal")]
    protein_g: Annotated[Decimal, Field(alias="proteinG")]
    carbohydrate_g: Annotated[Decimal, Field(alias="carbohydrateG")]
    fat_g: Annotated[Decimal, Field(alias="fatG")]
    basis_grams: Annotated[Decimal, Field(alias="basisGrams")]
    typical_serving_g: Annotated[Decimal | None, Field(alias="typicalServingG")]
    typical_serving_unit: Annotated[str | None, Field(alias="typicalServingUnit")]
    version: int

    @classmethod
    def from_row(cls, row: Any) -> OwnerFoodResponse:
        return cls(
            id=row.id,
            display_name=row.display_name,
            normalized_name=row.normalized_name,
            brand=row.brand,
            calories_kcal=row.calories_kcal,
            protein_g=row.protein_g,
            carbohydrate_g=row.carbohydrate_g,
            fat_g=row.fat_g,
            basis_grams=row.basis_grams,
            typical_serving_g=row.typical_serving_g,
            typical_serving_unit=row.typical_serving_unit,
            version=row.version,
        )


class FoodCandidateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    source: str  # "usda" or "owner"
    id: UUID
    description: Annotated[str, Field(alias="description")]
    brand_owner: Annotated[str | None, Field(alias="brandOwner")]
    serving_size_g: Annotated[Decimal | None, Field(alias="servingSizeG")]
    serving_unit: Annotated[str | None, Field(alias="servingUnit")]
    score: Decimal | None = None
    semantic_similarity: Annotated[Decimal | None, Field(alias="semanticSimilarity")] = None
    compatibility: str | None = None
    reasons: tuple[str, ...] = ()
    remembered: bool = False


class FoodSearchResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    query: str
    candidates: list[FoodCandidateResponse]


class OwnerFoodSelectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    remember_match: bool = Field(alias="rememberMatch", default=True)


class IngredientMatchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    food_reference_id: Annotated[UUID | None, Field(alias="foodReferenceId")] = None
    owner_food_id: Annotated[UUID | None, Field(alias="ownerFoodId")] = None
    grams_min: Annotated[Decimal | None, Field(alias="gramsMin")] = None
    grams_max: Annotated[Decimal | None, Field(alias="gramsMax")] = None
