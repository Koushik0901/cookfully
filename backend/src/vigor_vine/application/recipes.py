from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.application.jobs import JobService
from vigor_vine.domain.common import DomainError, require_version, utc_now, uuid7
from vigor_vine.domain.recipes import (
    IngredientInput,
    RecipeDraft,
)
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger, ErasureRecord
from vigor_vine.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from vigor_vine.infrastructure.models.nutrition import NutritionEstimate
from vigor_vine.infrastructure.models.recipes import Ingredient, Recipe, RecipeInstruction
from vigor_vine.infrastructure.repositories.recipes import RecipeRepository


@dataclass(frozen=True, slots=True)
class IngredientWrite:
    original_text: str
    quantity_min: Decimal | None = None
    quantity_max: Decimal | None = None
    unit_code: str | None = None
    unit_text: str | None = None
    food_name: str | None = None
    preparation: str | None = None
    comment: str | None = None
    purpose: str | None = None
    optional: bool = False


@dataclass(frozen=True, slots=True)
class RecipeWrite:
    title: str
    yield_quantity: Decimal
    ingredients: tuple[IngredientWrite, ...]
    instructions: tuple[str, ...]
    description: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    yield_unit: str = "servings"
    prep_minutes: int | None = None
    cook_minutes: int | None = None


@dataclass(frozen=True, slots=True)
class RecipeMutation:
    recipe: Recipe
    job: ProcessingJob | None


def recipe_input_hash(recipe_id: UUID, write: RecipeWrite) -> str:
    draft = RecipeDraft(
        id=recipe_id,
        title=write.title,
        yield_quantity=write.yield_quantity,
        ingredients=tuple(
            IngredientInput(
                item.original_text,
                item.quantity_min,
                item.unit_code,
                item.food_name,
                item.optional,
            )
            for item in write.ingredients
        ),
        instructions=write.instructions,
        status="draft",
        nutrition_state="pending",
    )
    return draft.input_hash()


class RecipeService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        erasure_ledger: ErasureLedger,
        *,
        source_instance_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._jobs = JobService(session_factory)
        self._ledger = erasure_ledger
        self._source_instance_id = source_instance_id

    def create(self, write: RecipeWrite, *, trace_id: str) -> RecipeMutation:
        self._validate(write)
        recipe_id = uuid7()
        input_hash = recipe_input_hash(recipe_id, write)
        with self._session_factory.begin() as session:
            recipe = Recipe(
                id=recipe_id,
                title=write.title.strip(),
                description=write.description,
                source_url=write.source_url,
                source_name=write.source_name,
                yield_quantity=write.yield_quantity,
                yield_unit=write.yield_unit,
                prep_minutes=write.prep_minutes,
                cook_minutes=write.cook_minutes,
                status="processing",
                nutrition_state="pending",
                input_hash=input_hash,
                version=1,
                ingredients=self._ingredients(recipe_id, write.ingredients),
                instructions=self._instructions(recipe_id, write.instructions),
            )
            RecipeRepository(session).add(recipe)
            job = self._jobs.accept_in_session(
                session,
                kind="ingredient_parse",
                aggregate_type="recipe",
                aggregate_id=recipe.id,
                input_hash=input_hash,
                trace_id=trace_id,
            )
            return RecipeMutation(recipe, job)

    def create_import_placeholder(self, url: str, *, trace_id: str) -> RecipeMutation:
        write = RecipeWrite(
            title="Importing recipe",
            yield_quantity=Decimal("1.000"),
            ingredients=(),
            instructions=(),
            source_url=url,
        )
        recipe_id = uuid7()
        input_hash = recipe_input_hash(recipe_id, write)
        with self._session_factory.begin() as session:
            recipe = Recipe(
                id=recipe_id,
                title=write.title,
                source_url=url,
                yield_quantity=write.yield_quantity,
                yield_unit="servings",
                status="processing",
                nutrition_state="pending",
                input_hash=input_hash,
                version=1,
            )
            RecipeRepository(session).add(recipe)
            job = self._jobs.accept_in_session(
                session,
                kind="recipe_import",
                aggregate_type="recipe",
                aggregate_id=recipe.id,
                input_hash=input_hash,
                trace_id=trace_id,
            )
            return RecipeMutation(recipe, job)

    def update(
        self,
        recipe_id: UUID,
        write: RecipeWrite,
        *,
        expected_version: int,
        trace_id: str,
    ) -> RecipeMutation:
        self._validate(write)
        with self._session_factory.begin() as session:
            repository = RecipeRepository(session)
            recipe = repository.get(recipe_id, for_update=True)
            if recipe.status == "archived":
                raise DomainError("recipe_archived", "Restore the recipe before editing it.", 409)
            require_version(expected_version, recipe.version)
            recipe.title = write.title.strip()
            recipe.description = write.description
            recipe.source_url = write.source_url
            recipe.source_name = write.source_name
            recipe.yield_quantity = write.yield_quantity
            recipe.yield_unit = write.yield_unit
            recipe.prep_minutes = write.prep_minutes
            recipe.cook_minutes = write.cook_minutes
            recipe.input_hash = recipe_input_hash(recipe_id, write)
            recipe.nutrition_state = "stale"
            recipe.status = "processing"
            recipe.version += 1
            repository.replace_content(
                recipe,
                self._ingredients(recipe_id, write.ingredients),
                self._instructions(recipe_id, write.instructions),
            )
            self._supersede_jobs(session, recipe_id)
            job = self._jobs.accept_in_session(
                session,
                kind="ingredient_parse",
                aggregate_type="recipe",
                aggregate_id=recipe.id,
                input_hash=recipe.input_hash,
                trace_id=trace_id,
            )
            return RecipeMutation(recipe, job)

    def archive(self, recipe_id: UUID, *, expected_version: int) -> Recipe:
        with self._session_factory.begin() as session:
            recipe = RecipeRepository(session).get(recipe_id, for_update=True)
            require_version(expected_version, recipe.version)
            if recipe.status not in {"draft", "processing", "ready", "partial", "failed"}:
                raise DomainError(
                    "invalid_archive_state", "This recipe cannot be archived now.", 409
                )
            prior_status = recipe.status
            if prior_status == "processing":
                if recipe.nutrition_state == "partial":
                    prior_status = "partial"
                elif recipe.active_estimate_id is not None:
                    prior_status = "ready"
                else:
                    prior_status = "draft"
            recipe.archived_from_status = prior_status
            recipe.status = "archived"
            recipe.archived_at = utc_now()
            recipe.version += 1
            self._supersede_jobs(session, recipe.id)
            return recipe

    def restore(self, recipe_id: UUID, *, expected_version: int) -> Recipe:
        with self._session_factory.begin() as session:
            recipe = RecipeRepository(session).get(recipe_id, for_update=True)
            require_version(expected_version, recipe.version)
            if recipe.status != "archived" or recipe.archived_from_status is None:
                raise DomainError(
                    "invalid_restore_state", "Only archived recipes can be restored.", 409
                )
            prior = recipe.archived_from_status
            estimate = (
                session.get(NutritionEstimate, recipe.active_estimate_id)
                if recipe.active_estimate_id
                else None
            )
            recipe.status = prior
            recipe.archived_at = None
            recipe.archived_from_status = None
            if estimate is None or estimate.input_hash != recipe.input_hash:
                recipe.nutrition_state = "stale"
            recipe.version += 1
            return recipe

    def permanent_delete(
        self,
        recipe_id: UUID,
        *,
        confirmed: bool,
        latest_backup_expiry: datetime,
    ) -> ErasureRecord:
        if not confirmed:
            raise DomainError(
                "confirmation_required", "Permanent deletion requires confirmation.", 422
            )
        with self._session_factory.begin() as session:
            repository = RecipeRepository(session)
            recipe = repository.get(recipe_id, for_update=True)
            if recipe.status != "archived":
                raise DomainError(
                    "archive_required",
                    "The recipe must be archived before permanent deletion.",
                    409,
                )
            self._supersede_jobs(session, recipe.id)
            record = self._ledger.append(
                subject_type="recipe",
                subject_id=recipe.id,
                scope="recipe_owned",
                source_instance_id=self._source_instance_id,
                latest_backup_expiry=latest_backup_expiry,
            )
            repository.permanently_delete(recipe)
            return record

    @staticmethod
    def _supersede_jobs(session: Session, recipe_id: UUID) -> None:
        now = utc_now()
        session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.aggregate_id == recipe_id,
                ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
            )
            .values(status="superseded", finished_at=now, next_retry_at=None)
        )

    @staticmethod
    def _validate(write: RecipeWrite) -> None:
        if not 1 <= len(write.title.strip()) <= 240:
            raise DomainError(
                "title_invalid", "Recipe title must contain 1 to 240 characters.", 422
            )
        if write.yield_quantity <= 0:
            raise DomainError("yield_invalid", "Recipe yield must be greater than zero.", 422)
        if write.prep_minutes is not None and write.prep_minutes < 0:
            raise DomainError("time_invalid", "Preparation time cannot be negative.", 422)
        if write.cook_minutes is not None and write.cook_minutes < 0:
            raise DomainError("time_invalid", "Cooking time cannot be negative.", 422)

    @staticmethod
    def _ingredients(recipe_id: UUID, values: tuple[IngredientWrite, ...]) -> list[Ingredient]:
        return [
            Ingredient(
                recipe_id=recipe_id,
                position=position,
                original_text=item.original_text,
                quantity_min=item.quantity_min,
                quantity_max=item.quantity_max,
                unit_code=item.unit_code,
                unit_text=item.unit_text,
                food_name=item.food_name,
                preparation=item.preparation,
                comment=item.comment,
                purpose=item.purpose,
                optional=item.optional,
                parse_status="manual" if item.food_name else "unparsed",
                version=1,
            )
            for position, item in enumerate(values)
        ]

    @staticmethod
    def _instructions(recipe_id: UUID, values: tuple[str, ...]) -> list[RecipeInstruction]:
        return [
            RecipeInstruction(recipe_id=recipe_id, position=position, text=value.strip())
            for position, value in enumerate(values)
            if value.strip()
        ]
