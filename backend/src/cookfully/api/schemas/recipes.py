from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
)

from cookfully.api.schemas.jobs import JobResponse
from cookfully.application.recipe_queries import (
    CorrectionRead,
    IngredientRead,
    NutritionRead,
    ProvenanceRead,
    RecipePageRead,
    RecipeRead,
)
from cookfully.application.recipes import IngredientWrite, RecipeWrite
from cookfully.domain.common import canonical_decimal, quantize_decimal
from cookfully.domain.nutrition import (
    MICRONUTRIENT_KEYS,
    USDA_MICRONUTRIENT_MANIFEST,
    MicronutrientKey,
    SupportedMicronutrientValue,
)


def _fixed_decimal(value: object, *, places: int, positive: bool = False) -> Decimal:
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        parsed = Decimal(value)
    else:
        raise ValueError("value must be a canonical non-negative decimal string")
    if parsed < 0 or (positive and parsed == 0):
        raise ValueError("value is out of range")
    exponent = -cast(int, parsed.as_tuple().exponent)
    if exponent > places:
        raise ValueError(f"value may contain at most {places} fractional places")
    return quantize_decimal(parsed, Decimal(1).scaleb(-places))


def _decimal6(value: object) -> Decimal:
    return _fixed_decimal(value, places=6)


def _serving(value: object) -> Decimal:
    return _fixed_decimal(value, places=3, positive=True)


Decimal6 = Annotated[
    Decimal,
    BeforeValidator(_decimal6),
    PlainSerializer(lambda value: canonical_decimal(value), return_type=str),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$",
        }
    ),
]
ServingDecimal = Annotated[
    Decimal,
    BeforeValidator(_serving),
    PlainSerializer(lambda value: canonical_decimal(value, places=3), return_type=str),
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^(?!0(?:\.0{1,3})?$)(?:0|[1-9][0-9]*)(?:\.[0-9]{1,3})?$",
        }
    ),
]


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class IngredientWriteRequest(ApiModel):
    original_text: str = Field(alias="originalText", min_length=1, max_length=1000)
    quantity_min: Decimal6 | None = Field(alias="quantityMin", default=None)
    quantity_max: Decimal6 | None = Field(alias="quantityMax", default=None)
    unit: str | None = Field(default=None, max_length=80)
    food: str | None = Field(default=None, max_length=240)
    preparation: str | None = Field(default=None, max_length=240)
    optional: bool = False

    def to_write(self) -> IngredientWrite:
        return IngredientWrite(
            original_text=self.original_text,
            quantity_min=self.quantity_min,
            quantity_max=self.quantity_max,
            unit_code=self.unit,
            unit_text=self.unit,
            food_name=self.food,
            preparation=self.preparation,
            optional=self.optional,
        )


class RecipeWriteRequest(ApiModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    source_url: AnyHttpUrl | None = Field(alias="sourceUrl", default=None, max_length=2048)
    yield_quantity: ServingDecimal = Field(alias="yieldQuantity")
    yield_unit: str = Field(alias="yieldUnit", default="servings", max_length=80)
    ingredients: tuple[IngredientWriteRequest, ...] = Field(min_length=1, max_length=500)
    instructions: tuple[str, ...] = Field(default=(), max_length=500)

    def to_write(self) -> RecipeWrite:
        return RecipeWrite(
            title=self.title,
            description=self.description,
            source_url=str(self.source_url) if self.source_url else None,
            yield_quantity=self.yield_quantity,
            yield_unit=self.yield_unit,
            ingredients=tuple(item.to_write() for item in self.ingredients),
            instructions=self.instructions,
        )


class ImportRecipeRequest(ApiModel):
    url: AnyHttpUrl = Field(max_length=2048)


class RecalculateRequest(ApiModel):
    reset_corrections: bool = Field(alias="resetCorrections", default=False)


class PermanentDeleteRequest(ApiModel):
    confirmation: Literal["permanently-delete"]


CorrectionField = Literal[
    "quantity_min",
    "quantity_max",
    "unit",
    "food_name",
    "food_reference",
    "grams",
    "yield_quantity",
    "calories_kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
]


class NutritionCorrectionWriteRequest(ApiModel):
    ingredient_id: UUID | None = Field(alias="ingredientId", default=None)
    field: CorrectionField
    decimal_value: Decimal6 | None = Field(alias="decimalValue", default=None)
    text_value: str | None = Field(alias="textValue", default=None, max_length=500)
    reference_id_value: UUID | None = Field(alias="referenceIdValue", default=None)
    reason: str | None = Field(default=None, max_length=1000)


class ProvenanceResponse(ApiModel):
    kind: str
    label: str
    source_url: str | None = Field(alias="sourceUrl", default=None)
    version: str | None = None

    @classmethod
    def from_read(cls, value: ProvenanceRead) -> ProvenanceResponse:
        return cls(
            kind=value.kind,
            label=value.label,
            source_url=value.source_url,
            version=value.version,
        )


class NutritionCorrectionResponse(ApiModel):
    id: UUID
    ingredient_id: UUID | None = Field(alias="ingredientId", default=None)
    field: str
    decimal_value: Decimal6 | None = Field(alias="decimalValue", default=None)
    text_value: str | None = Field(alias="textValue", default=None)
    reference_id_value: UUID | None = Field(alias="referenceIdValue", default=None)
    reason: str | None = None
    active: bool
    created_at: datetime = Field(alias="createdAt")

    @classmethod
    def from_read(cls, value: CorrectionRead) -> NutritionCorrectionResponse:
        return cls(
            id=value.id,
            ingredient_id=value.ingredient_id,
            field=value.field,
            decimal_value=value.decimal_value,
            text_value=value.text_value,
            reference_id_value=value.reference_id_value,
            reason=value.reason,
            active=value.active,
            created_at=value.created_at,
        )


class MicronutrientValueResponse(ApiModel):
    value: str | None
    unit: Literal["g", "mg", "ug"]
    explicit_zero: bool = Field(alias="explicitZero")
    coverage_ratio: str = Field(alias="coverageRatio")
    source: Literal["reference", "source", "manual", "unavailable"]
    mapping_version: str = Field(alias="mappingVersion")
    usda_nutrient_id: int = Field(alias="usdaNutrientId")

    @classmethod
    def from_value(cls, value: SupportedMicronutrientValue) -> MicronutrientValueResponse:
        source = (
            value.source if value.source in {"reference", "source", "manual"} else "unavailable"
        )
        return cls(
            value=canonical_decimal(value.value) if value.value is not None else None,
            unit=cast(Literal["g", "mg", "ug"], value.unit),
            explicit_zero=value.explicit_zero,
            coverage_ratio=canonical_decimal(value.coverage_ratio),
            source=cast(Literal["reference", "source", "manual", "unavailable"], source),
            mapping_version=value.mapping_version,
            usda_nutrient_id=value.fdc_nutrient_id,
        )


class MicronutrientsResponse(ApiModel):
    dietary_fiber_g: MicronutrientValueResponse = Field(alias="dietaryFiberG")
    sodium_mg: MicronutrientValueResponse = Field(alias="sodiumMg")
    potassium_mg: MicronutrientValueResponse = Field(alias="potassiumMg")
    calcium_mg: MicronutrientValueResponse = Field(alias="calciumMg")
    iron_mg: MicronutrientValueResponse = Field(alias="ironMg")
    magnesium_mg: MicronutrientValueResponse = Field(alias="magnesiumMg")
    vitamin_c_mg: MicronutrientValueResponse = Field(alias="vitaminCMg")
    vitamin_d_ug: MicronutrientValueResponse = Field(alias="vitaminDUg")
    vitamin_b12_ug: MicronutrientValueResponse = Field(alias="vitaminB12Ug")

    @classmethod
    def from_values(
        cls, values: Mapping[MicronutrientKey, SupportedMicronutrientValue]
    ) -> MicronutrientsResponse:
        return cls(
            dietary_fiber_g=MicronutrientValueResponse.from_value(values["dietary_fiber_g"]),
            sodium_mg=MicronutrientValueResponse.from_value(values["sodium_mg"]),
            potassium_mg=MicronutrientValueResponse.from_value(values["potassium_mg"]),
            calcium_mg=MicronutrientValueResponse.from_value(values["calcium_mg"]),
            iron_mg=MicronutrientValueResponse.from_value(values["iron_mg"]),
            magnesium_mg=MicronutrientValueResponse.from_value(values["magnesium_mg"]),
            vitamin_c_mg=MicronutrientValueResponse.from_value(values["vitamin_c_mg"]),
            vitamin_d_ug=MicronutrientValueResponse.from_value(values["vitamin_d_ug"]),
            vitamin_b12_ug=MicronutrientValueResponse.from_value(values["vitamin_b12_ug"]),
        )

    @classmethod
    def from_amounts(
        cls,
        amounts: Mapping[MicronutrientKey, Decimal | None],
        *,
        coverage_ratio: Decimal,
    ) -> MicronutrientsResponse:
        return cls.from_values(
            {
                key: SupportedMicronutrientValue(
                    key=key,
                    value=amounts.get(key),
                    unit=USDA_MICRONUTRIENT_MANIFEST[key].unit,
                    explicit_zero=amounts.get(key) == 0 if amounts.get(key) is not None else False,
                    source="reference" if amounts.get(key) is not None else "unavailable",
                    source_release=None,
                    mapping_version=USDA_MICRONUTRIENT_MANIFEST[key].mapping_version,
                    fdc_nutrient_id=USDA_MICRONUTRIENT_MANIFEST[key].fdc_nutrient_id,
                    input_hash="snapshot",
                    coverage_ratio=coverage_ratio,
                )
                for key in MICRONUTRIENT_KEYS
            }
        )


class ResolvedNutritionResponse(ApiModel):
    status: str
    basis_servings: ServingDecimal = Field(alias="basisServings")
    coverage_ratio: Decimal6 = Field(alias="coverageRatio")
    calories_kcal: Decimal6 | None = Field(alias="caloriesKcal", default=None)
    protein_g: Decimal6 | None = Field(alias="proteinG", default=None)
    carbohydrate_g: Decimal6 | None = Field(alias="carbohydrateG", default=None)
    fat_g: Decimal6 | None = Field(alias="fatG", default=None)
    micronutrients: MicronutrientsResponse
    provenance: tuple[ProvenanceResponse, ...]
    assumptions: tuple[str, ...] = ()
    corrections: tuple[NutritionCorrectionResponse, ...] = ()

    @classmethod
    def from_read(cls, value: NutritionRead) -> ResolvedNutritionResponse:
        return cls(
            status=value.status,
            basis_servings=value.basis_servings,
            coverage_ratio=value.coverage_ratio,
            calories_kcal=value.macros.calories_kcal,
            protein_g=value.macros.protein_g,
            carbohydrate_g=value.macros.carbohydrate_g,
            fat_g=value.macros.fat_g,
            micronutrients=MicronutrientsResponse.from_values(value.micronutrients),
            provenance=tuple(ProvenanceResponse.from_read(item) for item in value.provenance),
            assumptions=value.assumptions,
            corrections=tuple(
                NutritionCorrectionResponse.from_read(item) for item in value.corrections
            ),
        )


class IngredientResponse(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    original_text: str = Field(alias="originalText")
    quantity_min: Decimal6 | None = Field(alias="quantityMin", default=None)
    quantity_max: Decimal6 | None = Field(alias="quantityMax", default=None)
    unit: str | None = None
    food: str | None = None
    preparation: str | None = None
    optional: bool
    parse_status: str = Field(alias="parseStatus")
    match_status: str | None = Field(alias="matchStatus", default=None)
    assumptions: tuple[str, ...] = ()

    @classmethod
    def from_read(cls, value: IngredientRead) -> IngredientResponse:
        return cls(
            id=value.id,
            position=value.position,
            original_text=value.original_text,
            quantity_min=value.quantity_min,
            quantity_max=value.quantity_max,
            unit=value.unit,
            food=value.food,
            preparation=value.preparation,
            optional=value.optional,
            parse_status=value.parse_status,
            match_status=value.match_status,
            assumptions=value.assumptions,
        )


class RecipeResponse(ApiModel):
    id: UUID
    title: str
    source_url: str | None = Field(alias="sourceUrl", default=None)
    image_url: str | None = Field(alias="imageUrl", default=None)
    yield_quantity: ServingDecimal = Field(alias="yieldQuantity")
    yield_unit: str = Field(alias="yieldUnit")
    status: str
    archived_from_status: str | None = Field(alias="archivedFromStatus", default=None)
    nutrition_state: str = Field(alias="nutritionState")
    nutrition: ResolvedNutritionResponse | None = None
    version: int = Field(ge=1)
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_read(cls, value: RecipeRead) -> RecipeResponse:
        return cls(
            id=value.id,
            title=value.title,
            source_url=value.source_url,
            image_url=value.image_url,
            yield_quantity=value.yield_quantity,
            yield_unit=value.yield_unit,
            status=value.status,
            archived_from_status=value.archived_from_status,
            nutrition_state=value.nutrition_state,
            nutrition=(
                ResolvedNutritionResponse.from_read(value.nutrition) if value.nutrition else None
            ),
            version=value.version,
            updated_at=value.updated_at,
        )


class RecipeDetailResponse(RecipeResponse):
    description: str | None = None
    ingredients: tuple[IngredientResponse, ...]
    instructions: tuple[str, ...]
    active_job: JobResponse | None = Field(alias="activeJob", default=None)

    @classmethod
    def from_read(cls, value: RecipeRead) -> RecipeDetailResponse:
        base = RecipeResponse.from_read(value)
        return cls(
            **base.model_dump(),
            description=value.description,
            ingredients=tuple(IngredientResponse.from_read(item) for item in value.ingredients),
            instructions=value.instructions,
            active_job=(JobResponse.from_progress(value.active_job) if value.active_job else None),
        )


class RecipePageResponse(ApiModel):
    items: tuple[RecipeResponse, ...]
    next_cursor: str | None = Field(alias="nextCursor", default=None)

    @classmethod
    def from_read(cls, value: RecipePageRead) -> RecipePageResponse:
        return cls(
            items=tuple(RecipeResponse.from_read(item) for item in value.items),
            next_cursor=value.next_cursor,
        )
