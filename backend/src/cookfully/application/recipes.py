from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.food_matching import _tokens, normalize_food
from cookfully.application.jobs import JobService
from cookfully.domain.common import (
    NUTRIENT_SCALE,
    DomainError,
    quantize_decimal,
    require_version,
    utc_now,
    uuid7,
)
from cookfully.domain.recipes import (
    IngredientInput,
    RecipeDraft,
)
from cookfully.infrastructure.erasure_ledger import ErasureLedger, ErasureRecord
from cookfully.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.nutrition import (
    IngredientMatch,
    NutritionCorrection,
    NutritionEstimate,
)
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.recipes import (
    Ingredient,
    Recipe,
    RecipeInstruction,
    RecipeSection,
)
from cookfully.infrastructure.repositories.nutrition import NutritionRepository
from cookfully.infrastructure.repositories.owner_foods import UserFoodRepository
from cookfully.infrastructure.repositories.recipes import RecipeRepository


def _extract_food_from_text(original_text: str) -> str:
    """Heuristic: strip leading quantity and unit to extract the food name.

    Used during pre-matching when the ingredient has not been parsed yet
    (food_name is None) and we need a searchable name from the raw text.
    Safe — the pipeline's parser runs afterward and overwrites the ingredient
    fields with authoritative values; this is only for the pre-match pass.
    """

    text = original_text.strip()
    tokens = text.split()
    result_parts: list[str] = []
    for idx, token in enumerate(tokens):
        cleaned = token.rstrip(".,;:()")
        if idx <= 1 and (
            cleaned.replace(".", "").replace("/", "").replace(",", "").isdigit()
            or cleaned.casefold()
            in {
                "cup",
                "cups",
                "tablespoon",
                "tablespoons",
                "teaspoon",
                "teaspoons",
                "ounce",
                "ounces",
                "oz",
                "pound",
                "pounds",
                "lb",
                "lbs",
                "gram",
                "grams",
                "g",
                "kilogram",
                "kilograms",
                "kg",
                "milliliter",
                "milliliters",
                "ml",
                "liter",
                "liters",
                "l",
                "scoop",
                "scoops",
                "pinch",
                "dash",
                "can",
                "cans",
                "bunch",
                "package",
                "clove",
                "cloves",
            }
        ):
            continue
        result_parts.append(token)
    return " ".join(result_parts)


@dataclass(frozen=True, slots=True)
class SectionWrite:
    title: str


@dataclass(frozen=True, slots=True)
class InstructionWrite:
    text: str
    section_index: int | None = None


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
    section_index: int | None = None


@dataclass(frozen=True, slots=True)
class RecipeWrite:
    title: str
    yield_quantity: Decimal
    ingredients: tuple[IngredientWrite, ...]
    instructions: tuple[InstructionWrite, ...]
    sections: tuple[SectionWrite, ...] = ()
    description: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    yield_unit: str = "servings"
    prep_minutes: int | None = None
    cook_minutes: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instructions",
            tuple(
                item if isinstance(item, InstructionWrite) else InstructionWrite(text=item)
                for item in self.instructions
            ),
        )


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
        instructions=tuple(item.text for item in write.instructions),
        status="draft",
        nutrition_state="pending",
    )
    return draft.input_hash()


def _extract_unit_from_text(original_text: str) -> str | None:
    """Extract the likely unit token from an ingredient line's raw text."""

    tokens = original_text.strip().split()
    if len(tokens) < 2:
        return None
    return tokens[1].rstrip(".,;:()").casefold()


def _section_at(
    sections: Sequence[RecipeSection], section_index: int | None
) -> RecipeSection | None:
    if section_index is None:
        return None
    try:
        return sections[section_index]
    except IndexError:
        return None


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

    def create(self, write: RecipeWrite, *, trace_id: str, owner_id: UUID) -> RecipeMutation:
        self._validate(write)
        recipe_id = uuid7()
        input_hash = recipe_input_hash(recipe_id, write)
        with self._session_factory.begin() as session:
            sections = self._sections(recipe_id, write.sections)
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
                sections=sections,
                ingredients=self._ingredients(recipe_id, write.ingredients, sections),
                instructions=self._instructions(recipe_id, write.instructions, sections),
            )
            RecipeRepository(session).add(recipe)
            self._pre_match_owner_foods(session, recipe, owner_id, input_hash)
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
        owner_id: UUID,
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
            sections = self._sections(recipe_id, write.sections)
            repository.replace_content(
                recipe,
                sections,
                self._ingredients(recipe_id, write.ingredients, sections),
                self._instructions(recipe_id, write.instructions, sections),
            )
            self._supersede_jobs(session, recipe_id)
            self._pre_match_owner_foods(session, recipe, owner_id, recipe.input_hash)
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
        expected_version: int | None = None,
    ) -> ErasureRecord:
        if not confirmed:
            raise DomainError(
                "confirmation_required", "Permanent deletion requires confirmation.", 422
            )
        with self._session_factory.begin() as session:
            repository = RecipeRepository(session)
            recipe = repository.get(recipe_id, for_update=True)
            if expected_version is not None:
                require_version(expected_version, recipe.version)
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

    def recalculate(
        self,
        recipe_id: UUID,
        *,
        reset_corrections: bool,
        trace_id: str,
    ) -> RecipeMutation:
        with self._session_factory.begin() as session:
            recipe = RecipeRepository(session).get(recipe_id, for_update=True)
            if recipe.status == "archived":
                raise DomainError(
                    "recipe_archived", "Restore the recipe before recalculating it.", 409
                )
            self._supersede_jobs(session, recipe.id)
            if reset_corrections:
                session.execute(
                    update(NutritionCorrection)
                    .where(
                        NutritionCorrection.recipe_id == recipe.id,
                        NutritionCorrection.active.is_(True),
                    )
                    .values(active=False, reset_at=utc_now())
                )
            recipe.status = "processing"
            recipe.nutrition_state = "stale"
            recipe.version += 1
            job = self._jobs.accept_in_session(
                session,
                kind="ingredient_parse",
                aggregate_type="recipe",
                aggregate_id=recipe.id,
                input_hash=recipe.input_hash,
                trace_id=trace_id,
            )
            return RecipeMutation(recipe, job)

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
    def _pre_match_owner_foods(
        session: Session,
        recipe: Recipe,
        owner_id: UUID,
        input_hash: str,
    ) -> None:
        """Create manual IngredientMatch records for high-confidence owner food hits.

        Owner foods take priority over USDA reference foods. When a user has
        previously created a food (e.g., their specific whey protein brand),
        every future recipe import that names it gets the match for free.
        The pipeline's ``_match`` step skips ingredients whose active match
        has ``status == "manual"``, so these pre-matches short-circuit the
        USDA search entirely.
        """

        repo = UserFoodRepository(session)

        for ingredient in recipe.ingredients:
            food_name = ingredient.food_name or _extract_food_from_text(ingredient.original_text)
            parsed_unit = ingredient.unit_code or _extract_unit_from_text(ingredient.original_text)
            if not food_name.strip():
                continue
            query = normalize_food(food_name)
            candidates = repo.search(owner_id, query, limit=5)

            best_score: float = -1.0
            best_food: OwnerFood | None = None
            full_match_count = 0
            for candidate in candidates:
                candidate_tokens = _tokens(candidate.normalized_name)
                query_tokens = _tokens(query)
                query_set = set(query_tokens)
                candidate_set = set(candidate_tokens)
                intersection = query_set & candidate_set
                if not intersection:
                    continue
                if len(intersection) < len(query_set):
                    continue
                full_match_count += 1
                simple = len(intersection) / max(len(candidate_set), len(query_set))
                if simple > best_score:
                    best_score = simple
                    best_food = candidate

            if best_food is not None and (full_match_count == 1 or best_score >= 0.80):
                grams_min: Decimal | None = None
                grams_max: Decimal | None = None
                conversion_method: str | None = None
                assumption: str | None = None

                if (
                    best_food.typical_serving_g is not None
                    and best_food.typical_serving_unit is not None
                    and parsed_unit is not None
                    and parsed_unit.casefold() == best_food.typical_serving_unit.casefold()
                ):
                    grams_min = quantize_decimal(
                        ingredient.quantity_min * best_food.typical_serving_g
                        if ingredient.quantity_min is not None
                        else best_food.typical_serving_g,
                        NUTRIENT_SCALE,
                    )
                    grams_max = quantize_decimal(
                        ingredient.quantity_max * best_food.typical_serving_g
                        if ingredient.quantity_max is not None
                        else best_food.typical_serving_g,
                        NUTRIENT_SCALE,
                    )
                    conversion_method = "owner_serving"
                    assumption = (
                        f"1 {best_food.typical_serving_unit}"
                        f" = {best_food.typical_serving_g}g"
                        f" ({best_food.display_name})"
                    )

                NutritionRepository(session).activate_match(
                    IngredientMatch(
                        ingredient_id=ingredient.id,
                        food_reference_id=None,
                        owner_food_id=best_food.id,
                        status="manual",
                        match_method="manual",
                        match_score=None,
                        grams_min=grams_min,
                        grams_max=grams_max,
                        conversion_method=conversion_method,
                        assumption_text=assumption,
                        input_hash=input_hash,
                        active=True,
                    )
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
    def _sections(recipe_id: UUID, values: tuple[SectionWrite, ...]) -> list[RecipeSection]:
        return [
            RecipeSection(recipe_id=recipe_id, position=position, title=value.title.strip())
            for position, value in enumerate(values)
            if value.title.strip()
        ]

    @staticmethod
    def _ingredients(
        recipe_id: UUID,
        values: tuple[IngredientWrite, ...],
        sections: Sequence[RecipeSection],
    ) -> list[Ingredient]:
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
                section=_section_at(sections, item.section_index),
                version=1,
            )
            for position, item in enumerate(values)
        ]

    @staticmethod
    def _instructions(
        recipe_id: UUID,
        values: tuple[InstructionWrite, ...],
        sections: Sequence[RecipeSection],
    ) -> list[RecipeInstruction]:
        return [
            RecipeInstruction(
                recipe_id=recipe_id,
                position=position,
                text=value.text.strip(),
                section=_section_at(sections, value.section_index),
            )
            for position, value in enumerate(values)
            if value.text.strip()
        ]
