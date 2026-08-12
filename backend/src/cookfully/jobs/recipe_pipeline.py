from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import httpx
from billiard.exceptions import SoftTimeLimitExceeded  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.food_matching import FoodMatcher
from cookfully.application.jobs import JobService
from cookfully.application.recipes import (
    IngredientWrite,
    RecipeWrite,
    recipe_input_hash,
)
from cookfully.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal, utc_now
from cookfully.domain.nutrition import (
    MICRONUTRIENT_KEYS,
    USDA_MICRONUTRIENT_MANIFEST,
    IngredientNutrition,
    MacroValues,
    MicronutrientContribution,
    MicronutrientKey,
    SourceMicronutrient,
    rollup_micronutrients_per_serving,
    rollup_per_serving,
)
from cookfully.domain.units import IngredientMeasure, coverage_ratio, to_grams
from cookfully.domain.volume_assumptions import density_for
from cookfully.infrastructure.config import Settings, get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.ingredient_parser import parse_ingredient_line
from cookfully.infrastructure.media_store import MediaStore, StoredMedia
from cookfully.infrastructure.models.jobs import TERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.media import MediaAsset
from cookfully.infrastructure.models.nutrition import IngredientMatch, NutritionEstimate
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.recipes import Ingredient, Recipe, RecipeInstruction
from cookfully.infrastructure.models.reference_foods import FoodReference
from cookfully.infrastructure.observability import safe_log
from cookfully.infrastructure.recipe_images import RecipeImageService
from cookfully.infrastructure.recipe_importer import (
    ImportedRecipe,
    RecipeImporter,
    RecipeImportError,
)
from cookfully.infrastructure.repositories.nutrition import NutritionRepository
from cookfully.infrastructure.repositories.recipes import RecipeRepository
from cookfully.infrastructure.safe_fetch import SafeFetcher

logger = logging.getLogger(__name__)
RETRYABLE_CODES = frozenset({"dns_failed", "source_unavailable", "network_timeout"})
NEXT_KIND = {
    "recipe_import": "ingredient_parse",
    "ingredient_parse": "nutrition_match",
    "nutrition_match": "nutrition_rollup",
}
CORE_NUTRIENT_CODES = {
    "calories_kcal": ("208", "1008", "2047", "2048"),
    "protein_g": ("203", "1003"),
    "carbohydrate_g": ("205", "1005"),
    "fat_g": ("204", "1004"),
}


class JobEnvelope(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    schema_version: Annotated[int, Field(alias="schemaVersion", ge=1, le=1)]
    job_id: Annotated[UUID, Field(alias="jobId")]
    kind: str
    aggregate_type: Annotated[str, Field(alias="aggregateType")]
    aggregate_id: Annotated[UUID, Field(alias="aggregateId")]
    input_hash: Annotated[str, Field(alias="inputHash", min_length=8, max_length=128)]
    trace_id: Annotated[str, Field(alias="traceId", min_length=8, max_length=128)]
    requested_at: Annotated[datetime, Field(alias="requestedAt")]


@dataclass(frozen=True, slots=True)
class PipelineResult:
    job_id: UUID
    status: str
    next_job_id: UUID | None = None


class RecipePipeline:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        importer: RecipeImporter,
        image_service: RecipeImageService,
    ) -> None:
        self._session_factory = session_factory
        self._jobs = JobService(session_factory)
        self._importer = importer
        self._image_service = image_service

    async def process(self, envelope: JobEnvelope) -> PipelineResult:
        if envelope.aggregate_type != "recipe" or envelope.kind not in {
            "recipe_import",
            "ingredient_parse",
            "nutrition_match",
            "nutrition_rollup",
        }:
            raise DomainError("job_kind_unsupported", "This job kind is not supported.", 422)
        with self._session_factory() as session:
            job = session.get(ProcessingJob, envelope.job_id)
            recipe = session.get(Recipe, envelope.aggregate_id)
            if job is None:
                raise DomainError("job_not_found", "Job was not found.", 404)
            if job.kind != envelope.kind or job.aggregate_id != envelope.aggregate_id:
                raise DomainError(
                    "job_envelope_invalid", "Job envelope does not match storage.", 409
                )
            if job.status in TERMINAL_JOB_STATUSES:
                return PipelineResult(job.id, job.status)
            if job.status == "running":
                return PipelineResult(job.id, "running")
            current_hash = recipe.input_hash if recipe is not None else None

        claimed = self._jobs.claim(
            envelope.job_id,
            current_input_hash=current_hash,
        )
        if claimed.status in TERMINAL_JOB_STATUSES:
            return PipelineResult(claimed.id, claimed.status)
        try:
            if envelope.kind == "recipe_import":
                next_job = await self._import(envelope.job_id)
            elif envelope.kind == "ingredient_parse":
                next_job = self._parse(envelope.job_id)
            elif envelope.kind == "nutrition_match":
                next_job = self._match(envelope.job_id)
            else:
                next_job = self._rollup(envelope.job_id)
            return PipelineResult(
                envelope.job_id,
                "succeeded",
                next_job.id if next_job is not None else None,
            )
        except DomainError as exc:
            return self._fail(
                envelope.job_id,
                exc.code,
                retryable=exc.code in RETRYABLE_CODES,
                safe_message=exc.safe_message,
            )
        except (httpx.TimeoutException, TimeoutError):
            return self._fail(envelope.job_id, "network_timeout", retryable=True)
        except SoftTimeLimitExceeded:
            return self._fail(envelope.job_id, "attempt_timeout", retryable=True)
        except Exception:
            logger.exception(
                "recipe pipeline failed",
                extra={"job_id": str(envelope.job_id), "kind": envelope.kind},
            )
            return self._fail(
                envelope.job_id,
                "processing_error",
                retryable=False,
                safe_message="Recipe processing failed safely.",
            )

    async def _import(self, job_id: UUID) -> ProcessingJob | None:
        with self._session_factory() as session:
            job = self._running_job(session, job_id)
            recipe = self._recipe_for_job(session, job)
            if not recipe.source_url:
                raise DomainError("source_url_missing", "Recipe import has no source address.", 422)
            source_url = recipe.source_url

        try:
            imported = await self._importer.import_url(source_url)
        except RecipeImportError as exc:
            if exc.diagnostic is not None:
                with self._session_factory.begin() as session:
                    job = self._running_job(session, job_id)
                    recipe = self._recipe_for_job(session, job)
                    self._require_input(job, recipe)
                    self._persist_diagnostic(session, recipe.id, source_url, exc.diagnostic)
            raise
        stored_image: StoredMedia | None = None
        if imported.image_url:
            try:
                stored_image = await self._image_service.capture(imported.image_url)
            except DomainError:
                safe_log(
                    logger,
                    "recipe image skipped",
                    fields={"job_id": str(job_id), "reason": "image_unavailable"},
                )

        with self._session_factory.begin() as session:
            job = self._running_job(session, job_id)
            recipe = self._recipe_for_job(session, job)
            self._require_input(job, recipe)
            write = self._imported_write(imported)
            recipe.title = write.title
            recipe.source_url = imported.source_url
            recipe.canonical_source_url = imported.canonical_url
            recipe.source_name = write.source_name
            recipe.yield_quantity = write.yield_quantity
            recipe.yield_unit = write.yield_unit
            recipe.input_hash = recipe_input_hash(recipe.id, write)
            recipe.status = "processing"
            recipe.nutrition_state = "pending"
            recipe.version += 1
            RecipeRepository(session).replace_content(
                recipe,
                [
                    Ingredient(
                        recipe_id=recipe.id,
                        position=index,
                        original_text=item.original_text,
                        optional=item.optional,
                        parse_status="unparsed",
                        version=1,
                    )
                    for index, item in enumerate(write.ingredients)
                ],
                self._instructions(recipe.id, write.instructions),
            )
            if stored_image is not None:
                recipe.image_asset_id = self._persist_image(
                    session, recipe.id, imported.image_url, stored_image
                )
            self._persist_source_nutrition(session, recipe, imported)
            _, next_job = self._jobs.succeed_in_session(
                session,
                job.id,
                next_kind=NEXT_KIND[job.kind],
                next_input_hash=recipe.input_hash,
            )
            return next_job

    def _parse(self, job_id: UUID) -> ProcessingJob | None:
        with self._session_factory.begin() as session:
            job = self._running_job(session, job_id)
            recipe = self._recipe_for_job(session, job)
            self._require_input(job, recipe)
            for ingredient in recipe.ingredients:
                if ingredient.parse_status == "manual":
                    continue
                try:
                    parsed = parse_ingredient_line(ingredient.original_text)
                except Exception:
                    ingredient.parse_status = "failed"
                    continue
                ingredient.quantity_min = parsed.quantity_min
                ingredient.quantity_max = parsed.quantity_max
                ingredient.unit_code = parsed.unit_code
                ingredient.unit_text = parsed.unit_code
                ingredient.food_name = parsed.food_name
                ingredient.preparation = parsed.preparation
                ingredient.comment = parsed.comment
                ingredient.purpose = parsed.purpose
                ingredient.optional = parsed.optional
                ingredient.parse_status = "parsed"
                ingredient.parse_confidence = parsed.confidence
                ingredient.parser_name = parsed.parser_name
                ingredient.parser_version = parsed.parser_version
                ingredient.version += 1
            recipe.version += 1
            _, next_job = self._jobs.succeed_in_session(
                session, job.id, next_kind=NEXT_KIND[job.kind]
            )
            return next_job

    def _match(self, job_id: UUID) -> ProcessingJob | None:
        with self._session_factory.begin() as session:
            job = self._running_job(session, job_id)
            recipe = self._recipe_for_job(session, job)
            self._require_input(job, recipe)
            repository = NutritionRepository(session)
            active_types = {item.dataset_type for item in repository.active_datasets()}
            if not {"foundation", "sr_legacy"}.issubset(active_types):
                raise DomainError(
                    "reference_data_unavailable",
                    "Required nutrition reference data is not active.",
                    503,
                )
            matcher = FoodMatcher(repository)
            for ingredient in recipe.ingredients:
                active = repository.active_match(ingredient.id)
                if active is not None and active.status == "manual":
                    continue
                decision = matcher.decide(ingredient.food_name or "")
                candidate = decision.candidate
                density = (
                    density_for(candidate.food.description)
                    if candidate is not None
                    else density_for(ingredient.food_name or "")
                )
                grams_min, grams_max, method, assumption = self._grams(
                    ingredient, density_g_per_ml=density
                )
                repository.activate_match(
                    IngredientMatch(
                        ingredient_id=ingredient.id,
                        food_reference_id=(candidate.food.id if candidate is not None else None),
                        status=decision.status,
                        match_method=decision.method,
                        match_score=(candidate.score if candidate is not None else None),
                        grams_min=grams_min,
                        grams_max=grams_max,
                        conversion_method=method,
                        density_g_per_ml=density,
                        assumption_text=assumption,
                        source_release_id=(
                            candidate.food.dataset.release_id if candidate is not None else None
                        ),
                        input_hash=recipe.input_hash,
                        active=True,
                    )
                )
            recipe.version += 1
            _, next_job = self._jobs.succeed_in_session(
                session, job.id, next_kind=NEXT_KIND[job.kind]
            )
            return next_job

    def _rollup(self, job_id: UUID) -> ProcessingJob | None:
        with self._session_factory.begin() as session:
            job = self._running_job(session, job_id)
            recipe = self._recipe_for_job(session, job)
            self._require_input(job, recipe)
            matches = {
                item.ingredient_id: item
                for item in session.scalars(
                    select(IngredientMatch).where(
                        IngredientMatch.ingredient_id.in_(
                            ingredient.id for ingredient in recipe.ingredients
                        ),
                        IngredientMatch.active.is_(True),
                    )
                )
            }
            measures: list[IngredientMeasure] = []
            contributions: list[IngredientNutrition] = []
            micronutrient_contributions: list[MicronutrientContribution] = []
            assumptions: list[str] = []
            for ingredient in recipe.ingredients:
                match = matches.get(ingredient.id)
                grams = match.grams_min if match is not None else None
                matched = match is not None and (
                    match.food_reference_id is not None or match.owner_food_id is not None
                )
                measures.append(
                    IngredientMeasure(
                        grams,
                        match.grams_max if match else None,
                        "gram",
                        ingredient.optional,
                        matched,
                    )
                )
                if match is not None and match.assumption_text:
                    assumptions.append(f"{ingredient.position}: {match.assumption_text}")
                if not matched or grams is None:
                    continue
                assert match is not None
                if match.owner_food_id is not None:
                    owner_food = session.get(OwnerFood, match.owner_food_id)
                    if owner_food is None:
                        continue
                    contributions.append(
                        IngredientNutrition(
                            self._owner_food_macros(owner_food, grams), matched=True
                        )
                    )
                else:
                    food = session.get(FoodReference, match.food_reference_id)
                    if food is None:
                        continue
                    contributions.append(
                        IngredientNutrition(self._food_macros(food, grams), matched=True)
                    )
                    if not ingredient.optional:
                        micronutrient_contributions.append(
                            MicronutrientContribution(
                                self._food_micronutrients(food, grams),
                                mass_grams=grams,
                                resolved=True,
                            )
                        )
            coverage = coverage_ratio(measures).overall
            value = rollup_per_serving(
                contributions,
                recipe.yield_quantity,
                coverage=coverage,
            )
            required_measures = [item for item in measures if not item.optional]
            total_mass = sum(
                (item.minimum for item in required_measures if item.minimum is not None),
                Decimal(0),
            )
            micronutrients = rollup_micronutrients_per_serving(
                tuple(micronutrient_contributions),
                servings=recipe.yield_quantity,
                total_convertible_mass=total_mass,
                total_ingredient_count=len(required_measures),
                input_hash=recipe.input_hash,
                calculated_at=utc_now(),
            )
            complete = self._complete(value.macros)
            status = "estimated" if complete and coverage >= Decimal("0.900000") else "partial"
            existing = session.scalar(
                select(NutritionEstimate).where(
                    NutritionEstimate.recipe_id == recipe.id,
                    NutritionEstimate.input_hash == recipe.input_hash,
                    NutritionEstimate.pipeline_version == "nutrition-v1",
                )
            )
            estimate = existing or NutritionEstimate(
                recipe_id=recipe.id,
                status=status,
                basis_servings=value.basis_servings,
                calories_kcal=value.macros.calories_kcal,
                protein_g=value.macros.protein_g,
                carbohydrate_g=value.macros.carbohydrate_g,
                fat_g=value.macros.fat_g,
                fiber_g=micronutrients["dietary_fiber_g"].value,
                sodium_mg=micronutrients["sodium_mg"].value,
                potassium_mg=micronutrients["potassium_mg"].value,
                calcium_mg=micronutrients["calcium_mg"].value,
                iron_mg=micronutrients["iron_mg"].value,
                magnesium_mg=micronutrients["magnesium_mg"].value,
                vitamin_c_mg=micronutrients["vitamin_c_mg"].value,
                vitamin_d_ug=micronutrients["vitamin_d_ug"].value,
                vitamin_b12_ug=micronutrients["vitamin_b12_ug"].value,
                micronutrient_mapping_version=next(
                    iter(USDA_MICRONUTRIENT_MANIFEST.values())
                ).mapping_version,
                coverage_ratio=value.coverage,
                source_label="USDA FoodData Central",
                assumptions_summary="; ".join(assumptions) or None,
                input_hash=recipe.input_hash,
                pipeline_version="nutrition-v1",
                calculated_at=utc_now(),
            )
            active = (
                session.get(NutritionEstimate, recipe.active_estimate_id)
                if recipe.active_estimate_id
                else None
            )
            if (
                active is not None
                and active.status == "source_provided"
                and self._complete(self._estimate_macros(active))
            ):
                if existing is None:
                    session.add(estimate)
                recipe.status = "ready"
                recipe.nutrition_state = "source_provided"
            else:
                NutritionRepository(session).activate_estimate(recipe, estimate)
            recipe.version += 1
            self._jobs.succeed_in_session(session, job.id)
            return None

    def _fail(
        self,
        job_id: UUID,
        code: str,
        *,
        retryable: bool,
        safe_message: str | None = None,
    ) -> PipelineResult:
        with self._session_factory.begin() as session:
            if code == "stale_job_input":
                job = self._jobs.supersede_in_session(session, job_id)
                return PipelineResult(job.id, job.status)
            job = self._jobs.fail_attempt_in_session(
                session,
                job_id,
                code,
                retryable=retryable,
                safe_message=safe_message,
            )
            if job.status == "failed":
                recipe = session.get(Recipe, job.aggregate_id, with_for_update=True)
                if recipe is not None and recipe.input_hash == job.input_hash:
                    active = (
                        session.get(NutritionEstimate, recipe.active_estimate_id)
                        if recipe.active_estimate_id
                        else None
                    )
                    if active is not None and self._complete(self._estimate_macros(active)):
                        recipe.status = "ready"
                        recipe.nutrition_state = active.status
                    elif active is not None or recipe.ingredients:
                        recipe.status = "partial"
                        recipe.nutrition_state = "partial"
                    else:
                        recipe.status = "failed"
                        recipe.nutrition_state = "failed"
                    recipe.version += 1
            return PipelineResult(job.id, job.status)

    @staticmethod
    def _running_job(session: Session, job_id: UUID) -> ProcessingJob:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
        )
        if job is None:
            raise DomainError("job_not_found", "Job was not found.", 404)
        if job.status != "running":
            raise DomainError("job_not_running", "Job is not running.", 409)
        return job

    @staticmethod
    def _recipe_for_job(session: Session, job: ProcessingJob) -> Recipe:
        recipe = RecipeRepository(session).get(job.aggregate_id, for_update=True)
        return recipe

    @staticmethod
    def _require_input(job: ProcessingJob, recipe: Recipe) -> None:
        if recipe.input_hash != job.input_hash:
            raise DomainError("stale_job_input", "Recipe changed while processing.", 409)

    @staticmethod
    def _imported_write(imported: ImportedRecipe) -> RecipeWrite:
        return RecipeWrite(
            title=imported.title or "Imported recipe",
            yield_quantity=imported.yield_quantity or Decimal("1.000"),
            ingredients=tuple(IngredientWrite(original_text=line) for line in imported.ingredients),
            instructions=imported.instructions,
            source_url=imported.source_url,
            source_name=imported.canonical_url,
        )

    @staticmethod
    def _persist_image(
        session: Session,
        recipe_id: UUID,
        source_url: str | None,
        stored: StoredMedia,
    ) -> UUID:
        existing = session.scalar(
            select(MediaAsset).where(MediaAsset.storage_key == stored.storage_key)
        )
        if existing is not None:
            return existing.id
        asset = MediaAsset(
            recipe_id=recipe_id,
            kind="recipe_image",
            storage_key=stored.storage_key,
            content_type="image/webp",
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            source_url=source_url,
            encrypted=False,
            expires_at=None,
        )
        session.add(asset)
        session.flush()
        return asset.id

    @staticmethod
    def _persist_diagnostic(
        session: Session,
        recipe_id: UUID,
        source_url: str,
        stored: StoredMedia,
    ) -> UUID:
        existing = session.scalar(
            select(MediaAsset).where(MediaAsset.storage_key == stored.storage_key)
        )
        if existing is not None:
            return existing.id
        asset = MediaAsset(
            recipe_id=recipe_id,
            kind="failed_import_diagnostic",
            storage_key=stored.storage_key,
            content_type="text/html",
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            source_url=source_url,
            encrypted=True,
            expires_at=stored.expires_at,
        )
        session.add(asset)
        session.flush()
        return asset.id

    @classmethod
    def _persist_source_nutrition(
        cls, session: Session, recipe: Recipe, imported: ImportedRecipe
    ) -> None:
        macros = cls._source_macros(imported.source_nutrition)
        if all(
            value is None
            for value in (
                macros.calories_kcal,
                macros.protein_g,
                macros.carbohydrate_g,
                macros.fat_g,
            )
        ):
            return
        status = "source_provided" if cls._complete(macros) else "partial"
        estimate = NutritionEstimate(
            recipe_id=recipe.id,
            status=status,
            basis_servings=Decimal("1.000"),
            calories_kcal=macros.calories_kcal,
            protein_g=macros.protein_g,
            carbohydrate_g=macros.carbohydrate_g,
            fat_g=macros.fat_g,
            coverage_ratio=Decimal("1.000000") if cls._complete(macros) else Decimal("0.000000"),
            source_label=recipe.source_name or "Source recipe page",
            source_url=recipe.canonical_source_url,
            assumptions_summary="Source nutrition interpreted as per-serving values.",
            input_hash=recipe.input_hash,
            pipeline_version="source-v1",
            calculated_at=utc_now(),
        )
        session.add(estimate)
        session.flush()
        recipe.active_estimate_id = estimate.id
        recipe.nutrition_state = status

    @staticmethod
    def _source_macros(values: dict[str, str]) -> MacroValues:
        normalized = {re.sub(r"[^a-z]", "", key.casefold()): value for key, value in values.items()}

        def read(*keys: str) -> Decimal | None:
            raw = next((normalized[key] for key in keys if key in normalized), None)
            if raw is None:
                return None
            match = re.search(r"-?\d+(?:[.,]\d+)?", raw.replace(",", ""))
            if match is None:
                return None
            value = Decimal(match.group())
            return quantize_decimal(value, NUTRIENT_SCALE) if value >= 0 else None

        return MacroValues(
            read("calories", "caloriecontent", "energy"),
            read("protein", "proteincontent"),
            read("carbohydrates", "carbohydratecontent", "carbs"),
            read("fat", "fatcontent"),
        )

    @staticmethod
    def _grams(
        ingredient: Ingredient,
        *,
        density_g_per_ml: Decimal | None = None,
    ) -> tuple[Decimal | None, Decimal | None, str | None, str | None]:
        try:
            converted = to_grams(
                IngredientMeasure(
                    ingredient.quantity_min,
                    ingredient.quantity_max,
                    ingredient.unit_code,
                    ingredient.optional,
                ),
                density_g_per_ml=density_g_per_ml,
            )
        except DomainError:
            return None, None, None, None
        return converted.minimum, converted.maximum, converted.method, converted.assumption

    @staticmethod
    def _food_macros(food: FoodReference, grams: Decimal) -> MacroValues:
        nutrients = {item.nutrient_code: item.amount for item in food.nutrients}

        def value(field: str) -> Decimal | None:
            amount = next(
                (
                    nutrients[code]
                    for code in CORE_NUTRIENT_CODES[field]
                    if code in nutrients and nutrients[code] is not None
                ),
                None,
            )
            if amount is None:
                return None
            return quantize_decimal(amount * grams / food.basis_grams, NUTRIENT_SCALE)

        protein = value("protein_g")
        carbohydrates = value("carbohydrate_g")
        fat = value("fat_g")
        calories = value("calories_kcal")
        if calories is None and None not in (protein, carbohydrates, fat):
            calories = quantize_decimal(
                Decimal("4") * (protein or Decimal(0))
                + Decimal("4") * (carbohydrates or Decimal(0))
                + Decimal("9") * (fat or Decimal(0)),
                NUTRIENT_SCALE,
            )

        return MacroValues(calories, protein, carbohydrates, fat)

    @staticmethod
    def _owner_food_macros(food: OwnerFood, grams: Decimal) -> MacroValues:
        if food.basis_grams is None or food.basis_grams == 0:
            return MacroValues(
                quantize_decimal(food.calories_kcal, NUTRIENT_SCALE),
                quantize_decimal(food.protein_g, NUTRIENT_SCALE),
                quantize_decimal(food.carbohydrate_g, NUTRIENT_SCALE),
                quantize_decimal(food.fat_g, NUTRIENT_SCALE),
            )
        ratio = grams / food.basis_grams
        return MacroValues(
            quantize_decimal(food.calories_kcal * ratio, NUTRIENT_SCALE),
            quantize_decimal(food.protein_g * ratio, NUTRIENT_SCALE),
            quantize_decimal(food.carbohydrate_g * ratio, NUTRIENT_SCALE),
            quantize_decimal(food.fat_g * ratio, NUTRIENT_SCALE),
        )

    @staticmethod
    def _food_micronutrients(
        food: FoodReference, grams: Decimal
    ) -> dict[MicronutrientKey, SourceMicronutrient]:
        result: dict[MicronutrientKey, SourceMicronutrient] = {}
        for key in MICRONUTRIENT_KEYS:
            mapping = USDA_MICRONUTRIENT_MANIFEST[key]
            nutrient = next(
                (
                    item
                    for item in food.nutrients
                    if item.canonical_key == key
                    or item.nutrient_code in {str(mapping.fdc_nutrient_id), mapping.legacy_number}
                ),
                None,
            )
            if nutrient is None or nutrient.amount is None:
                continue
            result[key] = SourceMicronutrient(
                quantize_decimal(nutrient.amount * grams / food.basis_grams, NUTRIENT_SCALE),
                source="USDA FoodData Central",
                source_release=food.dataset.release_id,
                explicit=nutrient.explicit_zero,
            )
        return result

    @staticmethod
    def _complete(macros: MacroValues) -> bool:
        return all(
            value is not None
            for value in (
                macros.calories_kcal,
                macros.protein_g,
                macros.carbohydrate_g,
                macros.fat_g,
            )
        )

    @staticmethod
    def _estimate_macros(estimate: NutritionEstimate) -> MacroValues:
        return MacroValues(
            estimate.calories_kcal,
            estimate.protein_g,
            estimate.carbohydrate_g,
            estimate.fat_g,
        )

    @staticmethod
    def _instructions(recipe_id: UUID, values: tuple[str, ...]) -> list[RecipeInstruction]:
        return [
            RecipeInstruction(recipe_id=recipe_id, position=index, text=value)
            for index, value in enumerate(values)
            if value.strip()
        ]


@lru_cache
def get_recipe_pipeline() -> RecipePipeline:
    settings: Settings = get_settings()
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    media_store = MediaStore(settings.media_root, settings.secret_key.get_secret_value())
    importer = RecipeImporter(
        SafeFetcher(max_bytes=2 * 1024 * 1024),
        media_store,
        diagnostics_enabled=settings.failed_import_diagnostics_enabled,
    )
    images = RecipeImageService(SafeFetcher(max_bytes=10 * 1024 * 1024), media_store)
    return RecipePipeline(sessions, importer, images)
