from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobProgress, JobService
from cookfully.domain.common import DomainError
from cookfully.domain.nutrition import (
    MICRONUTRIENT_KEYS,
    USDA_MICRONUTRIENT_MANIFEST,
    MacroValues,
    MicronutrientAmounts,
    MicronutrientKey,
    NutrientField,
    NutritionCorrectionValue,
    SupportedMicronutrientValue,
    resolved_macros,
)
from cookfully.domain.recipes import ThumbnailCrop
from cookfully.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.nutrition import (
    IngredientMatch,
    NutritionCorrection,
    NutritionEstimate,
)
from cookfully.infrastructure.models.recipes import Ingredient, Recipe
from cookfully.infrastructure.repositories.nutrition import NutritionRepository
from cookfully.infrastructure.repositories.recipes import RecipeRepository


@dataclass(frozen=True, slots=True)
class ProvenanceRead:
    kind: str
    label: str
    source_url: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class CorrectionRead:
    id: UUID
    ingredient_id: UUID | None
    field: str
    decimal_value: Decimal | None
    text_value: str | None
    reference_id_value: UUID | None
    reason: str | None
    active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NutritionRead:
    status: str
    basis_servings: Decimal
    coverage_ratio: Decimal
    macros: MacroValues
    micronutrients: dict[MicronutrientKey, SupportedMicronutrientValue]
    provenance: tuple[ProvenanceRead, ...]
    assumptions: tuple[str, ...]
    corrections: tuple[CorrectionRead, ...]


@dataclass(frozen=True, slots=True)
class IngredientRead:
    id: UUID
    position: int
    original_text: str
    quantity_min: Decimal | None
    quantity_max: Decimal | None
    unit: str | None
    food: str | None
    preparation: str | None
    optional: bool
    parse_status: str
    match_status: str | None
    assumptions: tuple[str, ...]
    section_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InstructionRead:
    position: int
    text: str
    section_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SectionRead:
    id: UUID
    position: int
    title: str


@dataclass(frozen=True, slots=True)
class RecipeRead:
    id: UUID
    title: str
    description: str | None
    source_url: str | None
    image_url: str | None
    yield_quantity: Decimal
    yield_unit: str
    status: str
    archived_from_status: str | None
    nutrition_state: str
    nutrition: NutritionRead | None
    version: int
    updated_at: datetime
    favorite: bool = False
    collections: tuple[RecipeCollectionRead, ...] = ()
    meal_roles: tuple[str, ...] = ()
    ingredients: tuple[IngredientRead, ...] = ()
    instructions: tuple[InstructionRead, ...] = ()
    sections: tuple[SectionRead, ...] = ()
    active_job: JobProgress | None = None
    thumbnail_crop: ThumbnailCrop = field(default_factory=ThumbnailCrop)
    origin_kind: str = "manual"


@dataclass(frozen=True, slots=True)
class RecipePageRead:
    items: tuple[RecipeRead, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class RecipeCollectionRead:
    id: UUID
    name: str
    position: int


class RecipeQueryService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(
        self,
        *,
        query: str | None,
        nutrition_state: str | None,
        favorite: bool | None = None,
        collection_id: UUID | None = None,
        meal_role: str | None = None,
        include_archived: bool,
        cursor: str | None,
        limit: int,
    ) -> RecipePageRead:
        after = self._decode_cursor(cursor) if cursor else None
        with self._session_factory() as session:
            recipes = RecipeRepository(session).list_recipes(
                query=query,
                nutrition_state=nutrition_state,
                favorite=favorite,
                collection_id=collection_id,
                meal_role=meal_role,
                include_archived=include_archived,
                limit=limit + 1,
                after=after,
            )
            has_more = len(recipes) > limit
            recipes = recipes[:limit]
            items = tuple(self._read(session, recipe, detail=False) for recipe in recipes)
            next_cursor = (
                self._encode_cursor(recipes[-1].title.casefold(), recipes[-1].id)
                if has_more and recipes
                else None
            )
            return RecipePageRead(items, next_cursor)

    def get(self, recipe_id: UUID) -> RecipeRead:
        with self._session_factory() as session:
            recipe = RecipeRepository(session).get(recipe_id)
            return self._read(session, recipe, detail=True)

    def nutrition(self, recipe_id: UUID) -> NutritionRead:
        nutrition = self.get(recipe_id).nutrition
        assert nutrition is not None
        return nutrition

    def _read(self, session: Session, recipe: Recipe, *, detail: bool) -> RecipeRead:
        corrections = NutritionRepository(session).active_corrections(recipe.id)
        nutrition = self._nutrition(session, recipe, corrections)
        matches = {
            match.ingredient_id: match
            for match in session.scalars(
                select(IngredientMatch).where(
                    IngredientMatch.ingredient_id.in_(item.id for item in recipe.ingredients),
                    IngredientMatch.active.is_(True),
                )
            )
        }
        ingredients = (
            tuple(self._ingredient(item, matches.get(item.id)) for item in recipe.ingredients)
            if detail
            else ()
        )
        active_job = None
        if detail:
            job = session.scalar(
                select(ProcessingJob)
                .where(
                    ProcessingJob.aggregate_type == "recipe",
                    ProcessingJob.aggregate_id == recipe.id,
                    ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
                )
                .order_by(ProcessingJob.accepted_at.desc(), ProcessingJob.id.desc())
                .limit(1)
            )
            active_job = JobService._progress(job) if job is not None else None
        return RecipeRead(
            id=recipe.id,
            title=recipe.title,
            description=recipe.description,
            source_url=recipe.source_url,
            image_url=(f"/api/v1/media/{recipe.image_asset_id}" if recipe.image_asset_id else None),
            thumbnail_crop=ThumbnailCrop(
                recipe.thumbnail_focal_x, recipe.thumbnail_focal_y, recipe.thumbnail_zoom
            ),
            origin_kind=recipe.origin_kind,
            yield_quantity=recipe.yield_quantity,
            yield_unit=recipe.yield_unit,
            status=recipe.status,
            archived_from_status=recipe.archived_from_status,
            nutrition_state=recipe.nutrition_state,
            nutrition=nutrition,
            version=recipe.version,
            updated_at=recipe.updated_at,
            favorite=recipe.is_favorite,
            collections=tuple(
                RecipeCollectionRead(
                    item.collection.id, item.collection.name, item.collection.position
                )
                for item in sorted(
                    recipe.collection_memberships, key=lambda item: item.collection.position
                )
            ),
            meal_roles=tuple(sorted(item.role for item in recipe.meal_roles)),
            ingredients=ingredients,
            instructions=(
                tuple(
                    InstructionRead(
                        position=item.position,
                        text=item.text,
                        section_id=item.section_id,
                    )
                    for item in recipe.instructions
                )
                if detail
                else ()
            ),
            sections=(
                tuple(SectionRead(item.id, item.position, item.title) for item in recipe.sections)
                if detail
                else ()
            ),
            active_job=active_job,
        )

    @staticmethod
    def _nutrition(
        session: Session,
        recipe: Recipe,
        corrections: Sequence[NutritionCorrection],
    ) -> NutritionRead:
        estimate = (
            session.get(NutritionEstimate, recipe.active_estimate_id)
            if recipe.active_estimate_id
            else None
        )
        nutrient_corrections: dict[NutrientField, NutritionCorrectionValue] = {}
        for item in corrections:
            if (
                item.field
                in {
                    "calories_kcal",
                    "protein_g",
                    "carbohydrate_g",
                    "fat_g",
                }
                and item.decimal_value is not None
            ):
                nutrient_corrections[cast(NutrientField, item.field)] = NutritionCorrectionValue(
                    item.decimal_value, item.active
                )
        automatic = (
            MacroValues(
                estimate.calories_kcal,
                estimate.protein_g,
                estimate.carbohydrate_g,
                estimate.fat_g,
            )
            if estimate is not None
            else MacroValues(None, None, None, None)
        )
        resolved = resolved_macros(
            automatic,
            nutrient_corrections,
        )
        status = (
            "manual" if corrections else (estimate.status if estimate else recipe.nutrition_state)
        )
        provenance = (
            (
                ProvenanceRead(
                    "source" if estimate.status == "source_provided" else "reference",
                    estimate.source_label or "Nutrition estimate",
                    estimate.source_url,
                    estimate.pipeline_version,
                ),
            )
            if estimate is not None
            else ()
        )
        yield_correction = next(
            (
                item.decimal_value
                for item in corrections
                if item.field == "yield_quantity" and item.decimal_value is not None
            ),
            None,
        )
        micronutrient_corrections = {
            item.field: item.decimal_value
            for item in corrections
            if item.field in MICRONUTRIENT_KEYS and item.decimal_value is not None
        }
        return NutritionRead(
            status=status,
            basis_servings=(
                yield_correction
                or (estimate.basis_servings if estimate is not None else recipe.yield_quantity)
            ),
            coverage_ratio=(
                estimate.coverage_ratio if estimate is not None else Decimal("0.000000")
            ),
            macros=resolved.values,
            micronutrients=RecipeQueryService._micronutrients(estimate, micronutrient_corrections),
            provenance=provenance,
            assumptions=tuple(
                item.strip()
                for item in (
                    (estimate.assumptions_summary or "") if estimate is not None else ""
                ).split(";")
                if item.strip()
            ),
            corrections=tuple(RecipeQueryService._correction(item) for item in corrections),
        )

    @staticmethod
    def _micronutrients(
        estimate: NutritionEstimate | None,
        corrections: dict[MicronutrientKey, Decimal] | None = None,
    ) -> dict[MicronutrientKey, SupportedMicronutrientValue]:
        corrections = corrections or {}
        values: MicronutrientAmounts = {
            "dietary_fiber_g": estimate.fiber_g if estimate is not None else None,
            "sodium_mg": estimate.sodium_mg if estimate is not None else None,
            "potassium_mg": estimate.potassium_mg if estimate is not None else None,
            "calcium_mg": estimate.calcium_mg if estimate is not None else None,
            "iron_mg": estimate.iron_mg if estimate is not None else None,
            "magnesium_mg": estimate.magnesium_mg if estimate is not None else None,
            "vitamin_c_mg": estimate.vitamin_c_mg if estimate is not None else None,
            "vitamin_d_ug": estimate.vitamin_d_ug if estimate is not None else None,
            "vitamin_b12_ug": estimate.vitamin_b12_ug if estimate is not None else None,
        }
        coverage = estimate.coverage_ratio if estimate is not None else Decimal("0.000000")
        source = (
            "source"
            if estimate is not None and estimate.status == "source_provided"
            else "reference"
            if estimate is not None
            else "unavailable"
        )
        return {
            key: SupportedMicronutrientValue(
                key=key,
                value=corrections.get(key, values[key]),
                unit=USDA_MICRONUTRIENT_MANIFEST[key].unit,
                explicit_zero=(
                    corrections.get(key, values[key]) == 0
                    if corrections.get(key, values[key]) is not None
                    else False
                ),
                source="manual" if key in corrections else source,
                source_release=None,
                mapping_version=(
                    estimate.micronutrient_mapping_version
                    if estimate is not None and estimate.micronutrient_mapping_version
                    else USDA_MICRONUTRIENT_MANIFEST[key].mapping_version
                ),
                fdc_nutrient_id=USDA_MICRONUTRIENT_MANIFEST[key].fdc_nutrient_id,
                input_hash=estimate.input_hash if estimate is not None else "unavailable",
                coverage_ratio=coverage,
                calculated_at=estimate.calculated_at if estimate is not None else None,
            )
            for key in MICRONUTRIENT_KEYS
        }

    @staticmethod
    def _correction(value: NutritionCorrection) -> CorrectionRead:
        return CorrectionRead(
            value.id,
            value.ingredient_id,
            value.field,
            value.decimal_value,
            value.text_value,
            value.reference_id_value,
            value.reason,
            value.active,
            value.created_at,
        )

    @staticmethod
    def _ingredient(value: Ingredient, match: IngredientMatch | None) -> IngredientRead:
        assumptions = (
            (match.assumption_text,) if match is not None and match.assumption_text else ()
        )
        return IngredientRead(
            value.id,
            value.position,
            value.original_text,
            value.quantity_min,
            value.quantity_max,
            value.unit_code or value.unit_text,
            value.food_name,
            value.preparation,
            value.optional,
            value.parse_status,
            match.status if match is not None else None,
            assumptions,
            value.section_id,
        )

    @staticmethod
    def _encode_cursor(title: str, recipe_id: UUID) -> str:
        raw = json.dumps([title, str(recipe_id)], separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[str, UUID]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            title, raw_id = json.loads(base64.urlsafe_b64decode(padded).decode())
            if not isinstance(title, str):
                raise ValueError
            return title, UUID(raw_id)
        except (
            ValueError,
            TypeError,
            UnicodeDecodeError,
            binascii.Error,
            json.JSONDecodeError,
        ) as exc:
            raise DomainError("cursor_invalid", "Recipe cursor is invalid.", 422) from exc
