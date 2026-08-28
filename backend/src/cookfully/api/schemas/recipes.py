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
    model_validator,
)

from cookfully.api.schemas.jobs import JobResponse
from cookfully.application.recipe_organization import RecipeCollectionRead
from cookfully.application.recipe_queries import (
    CorrectionRead,
    IngredientRead,
    InstructionRead,
    NutritionRead,
    ProvenanceRead,
    RecipePageRead,
    RecipeRead,
    SectionRead,
)
from cookfully.application.recipe_queries import (
    RecipeCollectionRead as RecipeOrganizationCollectionRead,
)
from cookfully.application.recipes import (
    IngredientWrite,
    InstructionWrite,
    RecipeWrite,
    SectionWrite,
)
from cookfully.domain.common import canonical_decimal, quantize_decimal
from cookfully.domain.nutrition import (
    MICRONUTRIENT_KEYS,
    USDA_MICRONUTRIENT_MANIFEST,
    MicronutrientKey,
    SupportedMicronutrientValue,
)
from cookfully.domain.recipes import RecipeOrigin, ThumbnailCrop


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
    section: int | None = Field(default=None, ge=0)

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
            section_index=self.section,
        )


class SectionWriteRequest(ApiModel):
    title: str = Field(min_length=1, max_length=200)


class InstructionWriteRequest(ApiModel):
    text: str = Field(min_length=1, max_length=5000)
    section: int | None = Field(default=None, ge=0)


def _crop_fraction(value: object) -> Decimal:
    parsed = _fixed_decimal(value, places=6)
    if parsed < 0 or parsed > 1:
        raise ValueError("crop position must be between 0 and 1")
    return parsed


def _crop_size(value: object) -> Decimal:
    parsed = _fixed_decimal(value, places=6)
    if parsed <= 0 or parsed > 1:
        raise ValueError("crop size must be greater than 0 and at most 1")
    return parsed


CropFraction = Annotated[
    Decimal,
    BeforeValidator(_crop_fraction),
    PlainSerializer(lambda value: canonical_decimal(value), return_type=str),
]
CropSize = Annotated[
    Decimal,
    BeforeValidator(_crop_size),
    PlainSerializer(lambda value: canonical_decimal(value), return_type=str),
]


class ThumbnailCropRequest(ApiModel):
    x: CropFraction = Field(default=Decimal("0.000000"))
    y: CropFraction = Field(default=Decimal("0.000000"))
    width: CropSize = Field(default=Decimal("1.000000"))
    height: CropSize = Field(default=Decimal("1.000000"))

    @model_validator(mode="after")
    def _within_bounds(self) -> ThumbnailCropRequest:
        if self.x + self.width > Decimal("1"):
            raise ValueError("thumbnail crop extends past the right edge")
        if self.y + self.height > Decimal("1"):
            raise ValueError("thumbnail crop extends past the bottom edge")
        return self

    def to_domain(self) -> ThumbnailCrop:
        return ThumbnailCrop(self.x, self.y, self.width, self.height)


class RecipeWriteRequest(ApiModel):
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=5000)
    source_url: AnyHttpUrl | None = Field(alias="sourceUrl", default=None, max_length=2048)
    yield_quantity: ServingDecimal = Field(alias="yieldQuantity")
    yield_unit: str = Field(alias="yieldUnit", default="servings", max_length=80)
    prep_minutes: int | None = Field(alias="prepMinutes", default=None, ge=0, le=1440)
    cook_minutes: int | None = Field(alias="cookMinutes", default=None, ge=0, le=1440)
    ingredients: tuple[IngredientWriteRequest, ...] = Field(min_length=1, max_length=500)
    instructions: tuple[InstructionWriteRequest, ...] = Field(default=(), max_length=500)
    sections: tuple[SectionWriteRequest, ...] = Field(default=(), max_length=50)
    thumbnail_crop: ThumbnailCropRequest | None = Field(alias="thumbnailCrop", default=None)
    origin_kind: RecipeOrigin | None = Field(alias="originKind", default=None)
    staged_photo_id: UUID | None = Field(alias="stagedPhotoId", default=None)

    def to_write(self) -> RecipeWrite:
        return RecipeWrite(
            title=self.title,
            description=self.description,
            source_url=str(self.source_url) if self.source_url else None,
            yield_quantity=self.yield_quantity,
            yield_unit=self.yield_unit,
            prep_minutes=self.prep_minutes,
            cook_minutes=self.cook_minutes,
            ingredients=tuple(item.to_write() for item in self.ingredients),
            instructions=tuple(
                InstructionWrite(text=item.text, section_index=item.section)
                for item in self.instructions
            ),
            sections=tuple(SectionWrite(title=item.title) for item in self.sections),
            thumbnail_crop=self.thumbnail_crop.to_domain() if self.thumbnail_crop else None,
            origin_kind=self.origin_kind,
        )


class RecipePhotoStageResponse(ApiModel):
    id: UUID
    expires_at: datetime = Field(alias="expiresAt")


class RecipeBulkArchiveItem(ApiModel):
    id: UUID
    version: int = Field(ge=1)


class RecipeBulkArchiveRequest(ApiModel):
    recipes: tuple[RecipeBulkArchiveItem, ...] = Field(min_length=1, max_length=100)


class RecipeBulkArchiveResult(ApiModel):
    id: UUID
    status: Literal["archived", "already_archived", "failed"]
    version: int | None = Field(default=None, ge=1)
    code: str | None = None
    message: str | None = None


class RecipeBulkArchiveResponse(ApiModel):
    results: tuple[RecipeBulkArchiveResult, ...]


class ImportRecipeRequest(ApiModel):
    url: AnyHttpUrl = Field(max_length=2048)


class ImportPreviewRequest(ApiModel):
    url: AnyHttpUrl = Field(max_length=2048)


class ImportPreviewIngredient(ApiModel):
    original_text: str = Field(alias="originalText")
    needs_quantity: bool = Field(alias="needsQuantity")


class ImportPreviewSection(ApiModel):
    title: str | None = Field(default=None, max_length=200)
    ingredients: tuple[ImportPreviewIngredient, ...] = ()
    instructions: tuple[str, ...] = ()


class DuplicateSummary(ApiModel):
    id: UUID
    title: str
    version: int = Field(ge=1)


class ImportRecipePreview(ApiModel):
    parse_id: str = Field(alias="parseId")
    title: str = Field(max_length=240)
    yield_quantity: str | None = Field(alias="yieldQuantity", default=None)
    yield_text: str | None = Field(alias="yieldText", default=None)
    image_sources: tuple[str, ...] = Field(alias="imageSources")
    duplicates: tuple[DuplicateSummary, ...] = ()
    sections: tuple[ImportPreviewSection, ...] = ()


class ImportPreviewResponse(ApiModel):
    parse_id: str = Field(alias="parseId")
    title: str = Field(max_length=240)
    yield_quantity: str | None = Field(alias="yieldQuantity", default=None)
    yield_text: str | None = Field(alias="yieldText", default=None)
    image_sources: tuple[str, ...] = Field(alias="imageSources")
    duplicates: tuple[DuplicateSummary, ...] = ()
    sections: tuple[ImportPreviewSection, ...] = ()
    origin_kind: RecipeOrigin = Field(alias="originKind", default="web_import")
    recipes: tuple[ImportRecipePreview, ...] = ()


class ImportConfirmIngredient(ApiModel):
    original_text: str | None = Field(alias="originalText", default=None, max_length=1000)
    quantity_override: str | None = Field(alias="quantityOverride", default=None, max_length=200)
    optional: bool = False
    remove: bool = False


class ImportConfirmInstruction(ApiModel):
    text: str
    remove: bool = False


class ImportConfirmComponent(ApiModel):
    title: str | None = Field(default=None, max_length=200)
    ingredients: tuple[ImportConfirmIngredient, ...] = ()
    instructions: tuple[ImportConfirmInstruction, ...] = ()


class ImportConfirmRequest(ApiModel):
    parse_id: str = Field(alias="parseId", max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    # A web image URL is short, but PDF previews are selected as data URIs. Keep
    # the request bounded at the same limit as the dedicated photo-attach route
    # so a real PDF thumbnail can reach the best-effort attachment step.
    image_source: str | None = Field(alias="imageSource", default=None, max_length=20_000_000)
    image_source_kind: Literal["url", "pdf_thumbnail"] | None = Field(
        alias="imageSourceKind", default=None
    )
    yield_quantity: str | None = Field(alias="yieldQuantity", default=None, max_length=100)
    components: tuple[ImportConfirmComponent, ...] = ()
    thumbnail_crop: ThumbnailCropRequest | None = Field(alias="thumbnailCrop", default=None)

    @model_validator(mode="after")
    def validate_image_source_kind(self) -> ImportConfirmRequest:
        if self.image_source_kind == "pdf_thumbnail":
            if not self.image_source or not self.image_source.startswith("data:image/"):
                raise ValueError("A PDF thumbnail must be an image data URI.")
        elif (
            self.image_source_kind == "url" and self.image_source and len(self.image_source) > 2048
        ):
            raise ValueError("An image URL must be at most 2048 characters.")
        return self


class ImportMergeRequest(ApiModel):
    recipe_id: UUID = Field(alias="recipeId")
    parse_id: str = Field(alias="parseId", max_length=64)
    expected_version: int = Field(alias="expectedVersion", ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    yield_quantity: str | None = Field(alias="yieldQuantity", default=None, max_length=100)
    components: tuple[ImportConfirmComponent, ...] = ()


class RecipePhotoAttachRequest(ApiModel):
    image_source: str = Field(alias="imageSource", min_length=1, max_length=20_000_000)
    thumbnail_crop: ThumbnailCropRequest | None = Field(alias="thumbnailCrop", default=None)


class RecipeSourceImageChoiceRequest(ApiModel):
    url: AnyHttpUrl = Field(max_length=2048)
    thumbnail_crop: ThumbnailCropRequest | None = Field(alias="thumbnailCrop", default=None)


class RecipeSourceImageResponse(ApiModel):
    url: AnyHttpUrl


class RecalculateRequest(ApiModel):
    reset_corrections: bool = Field(alias="resetCorrections", default=False)


class PermanentDeleteRequest(ApiModel):
    confirmation: Literal["permanently-delete"]


class RecipeCollectionWriteRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    position: int | None = Field(default=None, ge=0)


class RecipeCollectionResponse(ApiModel):
    id: UUID
    name: str
    position: int
    version: int
    recipe_count: int = Field(alias="recipeCount")

    @classmethod
    def from_read(cls, value: RecipeCollectionRead) -> RecipeCollectionResponse:
        return cls(
            id=value.id,
            name=value.name,
            position=value.position,
            version=value.version,
            recipe_count=value.recipe_count,
        )


class RecipeOrganizationWriteRequest(ApiModel):
    favorite: bool
    collection_ids: tuple[UUID, ...] = Field(alias="collectionIds")
    meal_roles: tuple[Literal["breakfast", "lunch", "dinner", "snack"], ...] = Field(
        alias="mealRoles"
    )


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
    "dietary_fiber_g",
    "sodium_mg",
    "potassium_mg",
    "calcium_mg",
    "iron_mg",
    "magnesium_mg",
    "vitamin_c_mg",
    "vitamin_d_ug",
    "vitamin_b12_ug",
]


class NutritionCorrectionWriteRequest(ApiModel):
    ingredient_id: UUID | None = Field(alias="ingredientId", default=None)
    field: CorrectionField
    decimal_value: Decimal6 | None = Field(alias="decimalValue", default=None)
    text_value: str | None = Field(alias="textValue", default=None, max_length=500)
    reference_id_value: UUID | None = Field(alias="referenceIdValue", default=None)
    reason: str | None = Field(default=None, max_length=1000)
    remember_match: bool = Field(alias="rememberMatch", default=True)


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
    resolution_kind: str | None = Field(alias="resolutionKind", default=None)
    candidate_evidence: tuple[dict[str, object], ...] = Field(alias="candidateEvidence", default=())
    provisional_macros: dict[str, object] | None = Field(alias="provisionalMacros", default=None)
    assumptions: tuple[str, ...] = ()
    section_id: UUID | None = Field(alias="sectionId", default=None)

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
            resolution_kind=value.resolution_kind,
            candidate_evidence=value.candidate_evidence,
            provisional_macros=value.provisional_macros,
            assumptions=value.assumptions,
            section_id=value.section_id,
        )


class InstructionResponse(ApiModel):
    position: int = Field(ge=0)
    text: str
    section_id: UUID | None = Field(alias="sectionId", default=None)

    @classmethod
    def from_read(cls, value: InstructionRead) -> InstructionResponse:
        return cls(
            position=value.position,
            text=value.text,
            section_id=value.section_id,
        )


class SectionResponse(ApiModel):
    id: UUID
    position: int = Field(ge=0)
    title: str

    @classmethod
    def from_read(cls, value: SectionRead) -> SectionResponse:
        return cls(
            id=value.id,
            position=value.position,
            title=value.title,
        )


class RecipeCollectionSummaryResponse(ApiModel):
    id: UUID
    name: str
    position: int

    @classmethod
    def from_read(cls, value: RecipeOrganizationCollectionRead) -> RecipeCollectionSummaryResponse:
        return cls(id=value.id, name=value.name, position=value.position)


class RecipeResponse(ApiModel):
    id: UUID
    title: str
    source_url: str | None = Field(alias="sourceUrl", default=None)
    image_url: str | None = Field(alias="imageUrl", default=None)
    image_src_set: str | None = Field(alias="imageSrcSet", default=None)
    yield_quantity: ServingDecimal = Field(alias="yieldQuantity")
    yield_unit: str = Field(alias="yieldUnit")
    prep_minutes: int | None = Field(alias="prepMinutes", default=None, ge=0, le=1440)
    cook_minutes: int | None = Field(alias="cookMinutes", default=None, ge=0, le=1440)
    status: str
    archived_from_status: str | None = Field(alias="archivedFromStatus", default=None)
    nutrition_state: str = Field(alias="nutritionState")
    nutrition: ResolvedNutritionResponse | None = None
    version: int = Field(ge=1)
    updated_at: datetime = Field(alias="updatedAt")
    favorite: bool = False
    collections: tuple[RecipeCollectionSummaryResponse, ...] = ()
    meal_roles: tuple[Literal["breakfast", "lunch", "dinner", "snack"], ...] = Field(
        alias="mealRoles", default=()
    )
    thumbnail_crop: ThumbnailCropRequest = Field(alias="thumbnailCrop")
    origin_kind: RecipeOrigin = Field(alias="originKind")

    @classmethod
    def from_read(cls, value: RecipeRead) -> RecipeResponse:
        return cls(
            id=value.id,
            title=value.title,
            source_url=value.source_url,
            image_url=value.image_url,
            image_src_set=value.image_src_set,
            yield_quantity=value.yield_quantity,
            yield_unit=value.yield_unit,
            prep_minutes=value.prep_minutes,
            cook_minutes=value.cook_minutes,
            status=value.status,
            archived_from_status=value.archived_from_status,
            nutrition_state=value.nutrition_state,
            nutrition=(
                ResolvedNutritionResponse.from_read(value.nutrition) if value.nutrition else None
            ),
            version=value.version,
            updated_at=value.updated_at,
            favorite=value.favorite,
            collections=tuple(
                RecipeCollectionSummaryResponse.from_read(item) for item in value.collections
            ),
            meal_roles=tuple(
                cast(Literal["breakfast", "lunch", "dinner", "snack"], item)
                for item in value.meal_roles
            ),
            thumbnail_crop=ThumbnailCropRequest(
                x=value.thumbnail_crop.x,
                y=value.thumbnail_crop.y,
                width=value.thumbnail_crop.width,
                height=value.thumbnail_crop.height,
            ),
            origin_kind=cast(RecipeOrigin, value.origin_kind),
        )


class RecipeDetailResponse(RecipeResponse):
    description: str | None = None
    ingredients: tuple[IngredientResponse, ...]
    instructions: tuple[InstructionResponse, ...]
    sections: tuple[SectionResponse, ...] = ()
    active_job: JobResponse | None = Field(alias="activeJob", default=None)

    @classmethod
    def from_read(cls, value: RecipeRead) -> RecipeDetailResponse:
        base = RecipeResponse.from_read(value)
        return cls(
            **base.model_dump(),
            description=value.description,
            ingredients=tuple(IngredientResponse.from_read(item) for item in value.ingredients),
            instructions=tuple(InstructionResponse.from_read(item) for item in value.instructions),
            sections=tuple(SectionResponse.from_read(item) for item in value.sections),
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
