from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.grocery_lists import GroceryListService
from cookfully.application.recipe_queries import RecipeQueryService
from cookfully.domain.common import DomainError, require_version
from cookfully.domain.goals import (
    DailyGoal,
    GoalMode,
    reportable_macro_calorie_difference,
    week_start_for,
)
from cookfully.domain.goals import (
    MealTarget as MealTargetValue,
)
from cookfully.domain.meal_snapshots import (
    MealNutritionSnapshotValue,
    NutritionReliability,
    SnapshotSource,
    create_snapshot,
)
from cookfully.domain.nutrition import MacroValues
from cookfully.domain.plan_totals import PlannedSnapshot, PlanTotals, aggregate_plan
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.plans import (
    MealNutritionSnapshot,
    MealPlan,
    MealPlanEntry,
    MealTarget,
    UserGoal,
)
from cookfully.infrastructure.repositories.plans import GoalRepository, MealPlanRepository


@dataclass(frozen=True, slots=True)
class MealTargetWrite:
    meal_slot: str
    calories_kcal: Decimal | None
    protein_g: Decimal | None
    carbohydrate_g: Decimal | None
    fat_g: Decimal | None


@dataclass(frozen=True, slots=True)
class GoalWrite:
    mode: str
    maintenance_kcal: Decimal
    target_kcal: Decimal
    protein_g: Decimal
    carbohydrate_g: Decimal
    fat_g: Decimal
    effective_from: date
    effective_to: date | None
    meal_targets: tuple[MealTargetWrite, ...] = ()


@dataclass(frozen=True, slots=True)
class GoalRead:
    id: UUID
    mode: str
    maintenance_kcal: Decimal
    target_kcal: Decimal
    protein_g: Decimal
    carbohydrate_g: Decimal
    fat_g: Decimal
    effective_from: date
    effective_to: date | None
    meal_targets: tuple[MealTargetWrite, ...]
    macro_calorie_difference: Decimal | None
    version: int


@dataclass(frozen=True, slots=True)
class MealPlanEntryWrite:
    local_date: date
    meal_slot: str
    recipe_id: UUID
    servings: Decimal
    position: int | None = None
    refresh_nutrition: bool = False


@dataclass(frozen=True, slots=True)
class MealPlanEntryRead:
    id: UUID
    local_date: date
    meal_slot: str
    recipe_id: UUID | None
    recipe_title: str
    servings: Decimal
    position: int
    refresh_nutrition: bool
    nutrition: MealNutritionSnapshotValue
    origin: str
    version: int


@dataclass(frozen=True, slots=True)
class MealPlanEntryContext:
    week_start: date
    entry: MealPlanEntryRead


@dataclass(frozen=True, slots=True)
class MealPlanRead:
    id: UUID
    week_start: date
    timezone: str
    goal: GoalRead
    entries: tuple[MealPlanEntryRead, ...]
    totals: PlanTotals
    grocery_status: str
    version: int


class GoalService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, owner_id: UUID, on_date: date) -> GoalRead:
        with self._session_factory() as session:
            return self._read(GoalRepository(session).effective(owner_id, on_date))

    def put(
        self, owner_id: UUID, value: GoalWrite, *, expected_version: int | None = None
    ) -> GoalRead:
        validated = self._validate(value)
        try:
            with self._session_factory.begin() as session:
                repository = GoalRepository(session)
                existing = repository.starting(owner_id, value.effective_from, for_update=True)
                if existing is None:
                    if expected_version is not None:
                        raise DomainError("goal_not_found", "Goal was not found.", 404)
                    if repository.overlaps(owner_id, value.effective_from, value.effective_to):
                        raise DomainError(
                            "goal_period_overlap",
                            "Goal effective dates overlap an existing goal.",
                            409,
                        )
                    goal = UserGoal(owner_id=owner_id, version=1)
                    session.add(goal)
                else:
                    if expected_version is None:
                        raise DomainError(
                            "if_match_required", "If-Match is required to replace this goal.", 428
                        )
                    require_version(expected_version, existing.version)
                    if repository.overlaps(
                        owner_id,
                        value.effective_from,
                        value.effective_to,
                        exclude_id=existing.id,
                    ):
                        raise DomainError(
                            "goal_period_overlap",
                            "Goal effective dates overlap an existing goal.",
                            409,
                        )
                    goal = existing
                    goal.meal_targets.clear()
                    session.flush()
                    goal.version += 1
                self._apply(goal, validated)
                goal.meal_targets.extend(
                    MealTarget(
                        meal_slot=target.meal_slot,
                        calories_kcal=target.calories_kcal,
                        protein_g=target.protein_g,
                        carbohydrate_g=target.carbohydrate_g,
                        fat_g=target.fat_g,
                        position=position,
                    )
                    for position, target in enumerate(validated.meal_targets)
                )
                session.flush()
                result = self._read(goal)
            return result
        except IntegrityError as exc:
            raise DomainError(
                "goal_period_overlap", "Goal effective dates overlap an existing goal.", 409
            ) from exc

    @staticmethod
    def _validate(value: GoalWrite) -> DailyGoal:
        return DailyGoal(
            mode=cast(GoalMode, value.mode),
            maintenance_kcal=value.maintenance_kcal,
            target_kcal=value.target_kcal,
            protein_g=value.protein_g,
            carbohydrate_g=value.carbohydrate_g,
            fat_g=value.fat_g,
            effective_from=value.effective_from,
            effective_to=value.effective_to,
            meal_targets=tuple(
                MealTargetValue(
                    item.meal_slot,
                    item.calories_kcal,
                    item.protein_g,
                    item.carbohydrate_g,
                    item.fat_g,
                )
                for item in value.meal_targets
            ),
        )

    @staticmethod
    def _apply(goal: UserGoal, value: DailyGoal) -> None:
        goal.mode = value.mode
        goal.maintenance_kcal = value.maintenance_kcal
        goal.target_kcal = value.target_kcal
        goal.protein_g = value.protein_g
        goal.carbohydrate_g = value.carbohydrate_g
        goal.fat_g = value.fat_g
        goal.effective_from = value.effective_from
        goal.effective_to = value.effective_to

    @staticmethod
    def _read(goal: UserGoal) -> GoalRead:
        targets = tuple(
            MealTargetWrite(
                target.meal_slot,
                target.calories_kcal,
                target.protein_g,
                target.carbohydrate_g,
                target.fat_g,
            )
            for target in sorted(goal.meal_targets, key=lambda item: item.position)
        )
        return GoalRead(
            goal.id,
            goal.mode,
            goal.maintenance_kcal,
            goal.target_kcal,
            goal.protein_g,
            goal.carbohydrate_g,
            goal.fat_g,
            goal.effective_from,
            goal.effective_to,
            targets,
            reportable_macro_calorie_difference(
                target_kcal=goal.target_kcal,
                protein_g=goal.protein_g,
                carbohydrate_g=goal.carbohydrate_g,
                fat_g=goal.fat_g,
            ),
            goal.version,
        )


class MealPlanService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._recipes = RecipeQueryService(session_factory)

    def get(self, owner_id: UUID, week_start: date) -> MealPlanRead:
        with self._session_factory() as session:
            return self._read(MealPlanRepository(session).get_week(owner_id, week_start))

    def get_entry(self, owner_id: UUID, entry_id: UUID) -> MealPlanEntryContext:
        with self._session_factory() as session:
            entry = MealPlanRepository(session).get_entry(owner_id, entry_id)
            return MealPlanEntryContext(
                entry.meal_plan.week_start,
                self._entry_read(entry, entry.nutrition_snapshot),
            )

    def add(
        self,
        owner_id: UUID,
        week_start: date,
        value: MealPlanEntryWrite,
        *,
        origin: str = "manual",
    ) -> MealPlanEntryRead:
        if origin not in {"manual", "suggestion", "external"}:
            raise DomainError("plan_origin_invalid", "Meal-plan origin is invalid.", 422)
        source = self._source(value.recipe_id)
        nutrition = create_snapshot(source, value.servings)
        with self._session_factory.begin() as session:
            owner = self._owner(session, owner_id)
            self._validate_week(owner, week_start, value.local_date)
            repository = MealPlanRepository(session)
            plan = repository.find_week(owner_id, week_start)
            if plan is None:
                goal = GoalRepository(session).effective(owner_id, week_start)
                plan = MealPlan(
                    owner_id=owner_id,
                    week_start=week_start,
                    timezone=owner.timezone,
                    goal_id=goal.id,
                    version=1,
                )
                session.add(plan)
                session.flush()
            position = value.position
            if position is None:
                maximum = session.scalar(
                    select(func.max(MealPlanEntry.position)).where(
                        MealPlanEntry.meal_plan_id == plan.id,
                        MealPlanEntry.local_date == value.local_date,
                        MealPlanEntry.meal_slot == value.meal_slot,
                    )
                )
                position = (maximum if maximum is not None else -1) + 1
            self._ensure_position_available(
                session, plan.id, value.local_date, value.meal_slot, position
            )
            snapshot = self._snapshot_model(nutrition)
            session.add(snapshot)
            session.flush()
            entry = MealPlanEntry(
                meal_plan_id=plan.id,
                local_date=value.local_date,
                meal_slot=self._meal_slot(value.meal_slot),
                position=position,
                recipe_id=value.recipe_id,
                recipe_title_snapshot=source.recipe_title,
                servings=nutrition.basis_servings,
                nutrition_snapshot_id=snapshot.id,
                origin=origin,
                version=1,
            )
            session.add(entry)
            plan.version += 1
            GroceryListService.mark_dirty(session, plan.id)
            session.flush()
            return self._entry_read(entry, snapshot)

    def update(
        self,
        owner_id: UUID,
        entry_id: UUID,
        value: MealPlanEntryWrite,
        *,
        expected_version: int,
    ) -> MealPlanEntryRead:
        source = self._source(value.recipe_id)
        with self._session_factory.begin() as session:
            repository = MealPlanRepository(session)
            entry = repository.get_entry(owner_id, entry_id, for_update=True)
            require_version(expected_version, entry.version)
            owner = self._owner(session, owner_id)
            self._validate_week(owner, entry.meal_plan.week_start, value.local_date)
            position = value.position if value.position is not None else entry.position
            self._ensure_position_available(
                session,
                entry.meal_plan_id,
                value.local_date,
                value.meal_slot,
                position,
                exclude_id=entry.id,
            )
            replace = (
                value.refresh_nutrition
                or entry.recipe_id != value.recipe_id
                or entry.servings != value.servings
            )
            if replace:
                nutrition = create_snapshot(source, value.servings)
                snapshot = self._snapshot_model(nutrition)
                session.add(snapshot)
                session.flush()
                entry.nutrition_snapshot_id = snapshot.id
            else:
                snapshot = entry.nutrition_snapshot
            entry.local_date = value.local_date
            entry.meal_slot = self._meal_slot(value.meal_slot)
            entry.position = position
            entry.recipe_id = value.recipe_id
            entry.recipe_title_snapshot = source.recipe_title
            entry.servings = create_snapshot(source, value.servings).basis_servings
            entry.version += 1
            entry.meal_plan.version += 1
            GroceryListService.mark_dirty(session, entry.meal_plan_id)
            session.flush()
            return self._entry_read(entry, snapshot)

    def remove(self, owner_id: UUID, entry_id: UUID, *, expected_version: int) -> None:
        with self._session_factory.begin() as session:
            entry = MealPlanRepository(session).get_entry(owner_id, entry_id, for_update=True)
            require_version(expected_version, entry.version)
            entry.meal_plan.version += 1
            GroceryListService.mark_dirty(session, entry.meal_plan_id)
            session.execute(delete(MealPlanEntry).where(MealPlanEntry.id == entry.id))

    def _source(self, recipe_id: UUID) -> SnapshotSource:
        recipe = self._recipes.get(recipe_id)
        if recipe.status == "archived":
            raise DomainError("recipe_archived", "Restore the recipe before planning it.", 409)
        if recipe.nutrition_state == "stale":
            raise DomainError(
                "recipe_nutrition_stale",
                "Recalculate recipe nutrition before adding it to a plan.",
                409,
            )
        nutrition = recipe.nutrition
        if nutrition is None or nutrition.status not in {
            "source_provided",
            "estimated",
            "partial",
            "manual",
        }:
            raise DomainError(
                "recipe_nutrition_unavailable",
                "Recipe nutrition must be resolved before it can be planned.",
                409,
            )
        return SnapshotSource(
            recipe_id=recipe.id,
            estimate_id=None,
            recipe_title=recipe.title,
            macros=nutrition.macros,
            status=cast(NutritionReliability, nutrition.status),
            coverage_ratio=nutrition.coverage_ratio,
            micronutrients={key: item.value for key, item in nutrition.micronutrients.items()},
        )

    @staticmethod
    def _owner(session: Session, owner_id: UUID) -> OwnerAccount:
        owner = session.get(OwnerAccount, owner_id)
        if owner is None:
            raise DomainError("owner_not_found", "Owner account was not found.", 404)
        return owner

    @staticmethod
    def _validate_week(owner: OwnerAccount, week_start: date, local_date: date) -> None:
        if week_start_for(week_start, owner.week_starts_on) != week_start:
            raise DomainError(
                "week_start_invalid", "Date does not match the configured week start.", 422
            )
        if not week_start <= local_date <= week_start + timedelta(days=6):
            raise DomainError(
                "plan_date_outside_week", "Entry date must be inside the plan week.", 422
            )

    @staticmethod
    def _meal_slot(value: str) -> str:
        result = value.strip()
        if not result:
            raise DomainError("meal_slot_required", "Meal slot is required.", 422)
        return result

    @staticmethod
    def _ensure_position_available(
        session: Session,
        plan_id: UUID,
        local_date: date,
        meal_slot: str,
        position: int,
        *,
        exclude_id: UUID | None = None,
    ) -> None:
        if position < 0:
            raise DomainError("position_negative", "Entry position cannot be negative.", 422)
        statement = select(MealPlanEntry.id).where(
            MealPlanEntry.meal_plan_id == plan_id,
            MealPlanEntry.local_date == local_date,
            MealPlanEntry.meal_slot == meal_slot.strip(),
            MealPlanEntry.position == position,
        )
        if exclude_id is not None:
            statement = statement.where(MealPlanEntry.id != exclude_id)
        if session.scalar(statement) is not None:
            raise DomainError("entry_position_conflict", "Meal slot position is already used.", 409)

    @staticmethod
    def _snapshot_model(value: MealNutritionSnapshotValue) -> MealNutritionSnapshot:
        return MealNutritionSnapshot(
            recipe_id=value.recipe_id,
            estimate_id=value.estimate_id,
            basis_servings=value.basis_servings,
            calories_kcal=value.calories_kcal,
            protein_g=value.protein_g,
            carbohydrate_g=value.carbohydrate_g,
            fat_g=value.fat_g,
            dietary_fiber_g=value.micronutrients["dietary_fiber_g"],
            sodium_mg=value.micronutrients["sodium_mg"],
            potassium_mg=value.micronutrients["potassium_mg"],
            calcium_mg=value.micronutrients["calcium_mg"],
            iron_mg=value.micronutrients["iron_mg"],
            magnesium_mg=value.micronutrients["magnesium_mg"],
            vitamin_c_mg=value.micronutrients["vitamin_c_mg"],
            vitamin_d_ug=value.micronutrients["vitamin_d_ug"],
            vitamin_b12_ug=value.micronutrients["vitamin_b12_ug"],
            nutrition_state=value.status,
            coverage_ratio=value.coverage_ratio,
        )

    @staticmethod
    def _snapshot_value(value: MealNutritionSnapshot) -> MealNutritionSnapshotValue:
        return MealNutritionSnapshotValue(
            value.recipe_id,
            value.estimate_id,
            "",
            value.basis_servings,
            value.calories_kcal,
            value.protein_g,
            value.carbohydrate_g,
            value.fat_g,
            cast(NutritionReliability, value.nutrition_state),
            value.coverage_ratio,
            {
                "dietary_fiber_g": value.dietary_fiber_g,
                "sodium_mg": value.sodium_mg,
                "potassium_mg": value.potassium_mg,
                "calcium_mg": value.calcium_mg,
                "iron_mg": value.iron_mg,
                "magnesium_mg": value.magnesium_mg,
                "vitamin_c_mg": value.vitamin_c_mg,
                "vitamin_d_ug": value.vitamin_d_ug,
                "vitamin_b12_ug": value.vitamin_b12_ug,
            },
        )

    @classmethod
    def _entry_read(
        cls, entry: MealPlanEntry, snapshot: MealNutritionSnapshot
    ) -> MealPlanEntryRead:
        nutrition = cls._snapshot_value(snapshot)
        nutrition = MealNutritionSnapshotValue(
            nutrition.recipe_id,
            nutrition.estimate_id,
            entry.recipe_title_snapshot,
            nutrition.basis_servings,
            nutrition.calories_kcal,
            nutrition.protein_g,
            nutrition.carbohydrate_g,
            nutrition.fat_g,
            nutrition.status,
            nutrition.coverage_ratio,
            nutrition.micronutrients,
        )
        return MealPlanEntryRead(
            entry.id,
            entry.local_date,
            entry.meal_slot,
            entry.recipe_id,
            entry.recipe_title_snapshot,
            entry.servings,
            entry.position,
            False,
            nutrition,
            entry.origin,
            entry.version,
        )

    @classmethod
    def _read(cls, plan: MealPlan) -> MealPlanRead:
        entries = tuple(cls._entry_read(entry, entry.nutrition_snapshot) for entry in plan.entries)
        totals = aggregate_plan(
            [
                PlannedSnapshot(entry.local_date, entry.meal_slot, entry.position, entry.nutrition)
                for entry in entries
            ],
            daily_target=MacroValues(
                plan.goal.target_kcal,
                plan.goal.protein_g,
                plan.goal.carbohydrate_g,
                plan.goal.fat_g,
            ),
        )
        return MealPlanRead(
            plan.id,
            plan.week_start,
            plan.timezone,
            GoalService._read(plan.goal),
            entries,
            totals,
            plan.grocery_list.status if plan.grocery_list is not None else "absent",
            plan.version,
        )
