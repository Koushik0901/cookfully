from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from cookfully.application.grocery_lists import GroceryListService
from cookfully.application.jobs import JobService
from cookfully.application.meal_plans import MealPlanRead, MealPlanService
from cookfully.application.recipe_queries import RecipeQueryService, RecipeRead
from cookfully.domain.common import (
    NUTRIENT_SCALE,
    DomainError,
    canonical_decimal,
    quantize_decimal,
    require_version,
    today_in_timezone,
    utc_now,
)
from cookfully.domain.goals import week_start_for
from cookfully.domain.meal_snapshots import (
    NutritionReliability,
    SnapshotSource,
    create_snapshot,
)
from cookfully.domain.nutrition import MacroValues
from cookfully.domain.plan_totals import PeriodTotal, PlannedSnapshot, aggregate_plan
from cookfully.domain.suggestion_solver import (
    SuggestionCandidate,
    SuggestionProblem,
    SuggestionSolution,
    SuggestionTarget,
    solve_suggestion,
)
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.plans import MealNutritionSnapshot, MealPlan, MealPlanEntry
from cookfully.infrastructure.models.suggestions import SuggestionItem, SuggestionRun
from cookfully.infrastructure.repositories.plans import GoalRepository, MealPlanRepository

SOLVER_VERSION = "cp-sat-v1"
SUGGESTION_TTL = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class SuggestionWrite:
    scope: str
    week_start: date
    local_date: date | None
    meal_slot: str | None
    tolerances: SuggestionTarget
    excluded_recipe_ids: frozenset[UUID]
    required_recipe_ids: frozenset[UUID]
    max_recipe_repetitions: int


@dataclass(frozen=True, slots=True)
class SuggestionAccepted:
    suggestion_id: UUID
    job_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class SuggestionItemRead:
    id: UUID
    recipe_id: UUID | None
    recipe_title: str
    local_date: date
    meal_slot: str
    servings: Decimal
    calories_kcal: Decimal
    protein_g: Decimal
    carbohydrate_g: Decimal
    fat_g: Decimal
    nutrition_state: str
    coverage_ratio: Decimal
    accepted: bool


@dataclass(frozen=True, slots=True)
class SuggestionRead:
    id: UUID
    status: str
    request: SuggestionWrite
    target: SuggestionTarget
    items: tuple[SuggestionItemRead, ...]
    projected_day_totals: dict[str, object]
    projected_week_total: dict[str, object] | None
    missed_constraints: tuple[str, ...]
    unmet_constraint_count: int | None
    objective_score: Decimal | None
    distance_components: dict[str, Decimal | int] | None
    plan_version: int
    failure_code: str | None
    created_at: datetime
    expires_at: datetime | None


class SuggestionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._jobs = JobService(session_factory)
        self._recipes = RecipeQueryService(session_factory)
        self._plans = MealPlanService(session_factory)

    def request(
        self, owner_id: UUID, value: SuggestionWrite, *, trace_id: str
    ) -> SuggestionAccepted:
        now = utc_now()
        with self._session_factory.begin() as session:
            owner = session.get(OwnerAccount, owner_id)
            if owner is None:
                raise DomainError("owner_not_found", "Owner account was not found.", 404)
            value = self._validate(value, owner)
            plan = self._ensure_plan(session, owner_id, value.week_start)
            target = self._remaining_target(plan, value)
            fingerprint = self._input_hash(plan, value, target)
            run = SuggestionRun(
                owner_id=owner_id,
                meal_plan_id=plan.id,
                scope=value.scope,
                week_start=value.week_start,
                local_date=value.local_date,
                meal_slot=value.meal_slot,
                plan_version=plan.version,
                target_calories_kcal=target.calories_kcal,
                target_protein_g=target.protein_g,
                target_carbohydrate_g=target.carbohydrate_g,
                target_fat_g=target.fat_g,
                tolerance_calories_kcal=value.tolerances.calories_kcal,
                tolerance_protein_g=value.tolerances.protein_g,
                tolerance_carbohydrate_g=value.tolerances.carbohydrate_g,
                tolerance_fat_g=value.tolerances.fat_g,
                excluded_recipe_ids=sorted(value.excluded_recipe_ids, key=str),
                required_recipe_ids=sorted(value.required_recipe_ids, key=str),
                max_recipe_repetitions=value.max_recipe_repetitions,
                solver_version=SOLVER_VERSION,
                time_limit_seconds=8,
                input_hash=fingerprint,
                status="queued",
                missed_constraints=[],
                ordered_recipe_ids=[],
                projected_day_totals={},
                expires_at=now + SUGGESTION_TTL,
            )
            session.add(run)
            session.flush()
            job = self._jobs.accept_in_session(
                session,
                kind="suggestion",
                aggregate_type="suggestion",
                aggregate_id=run.id,
                input_hash=fingerprint,
                trace_id=trace_id,
                now=now,
            )
            run.job_id = job.id
            return SuggestionAccepted(run.id, job.id, run.status)

    def run_job(self, job_id: UUID) -> SuggestionRead:
        job = self._jobs.claim(job_id)
        if job.status != "running":
            return self.get(job.aggregate_id)
        try:
            with self._session_factory.begin() as session:
                run = self._get_model(session, job.aggregate_id, for_update=True)
                plan = MealPlanRepository(session).get_week(
                    run.owner_id, run.week_start, for_update=True
                )
                if plan.version != run.plan_version:
                    run.status = "failed"
                    run.failure_code = "stale_plan"
                    raise DomainError("stale_plan", "The meal plan changed before solving.", 409)
                run.status = "running"
            recipes = self._candidate_recipes()
            with self._session_factory() as session:
                run = self._get_model(session, job.aggregate_id)
                plan = MealPlanRepository(session).get_week(run.owner_id, run.week_start)
                problem = self._problem(run, plan, recipes)
            solution = solve_suggestion(problem)
            if solution.status == "timeout":
                raise DomainError(
                    "solver_timeout", "Suggestion solving reached its time limit.", 503
                )
            with self._session_factory.begin() as session:
                run = self._get_model(session, job.aggregate_id, for_update=True)
                plan = MealPlanRepository(session).get_week(run.owner_id, run.week_start)
                if plan.version != run.plan_version:
                    run.status = "failed"
                    run.failure_code = "stale_plan"
                    raise DomainError("stale_plan", "The meal plan changed before solving.", 409)
                self._store_solution(session, run, plan, solution, recipes)
            self._jobs.succeed(job.id)
            return self.get(job.aggregate_id)
        except DomainError as exc:
            with self._session_factory.begin() as session:
                run = self._get_model(session, job.aggregate_id, for_update=True)
                run.status = "failed"
                run.failure_code = exc.code
            self._jobs.fail_attempt(
                job.id,
                exc.code,
                retryable=exc.code == "solver_timeout",
                safe_message=exc.safe_message,
            )
            raise
        except Exception:
            with self._session_factory.begin() as session:
                run = self._get_model(session, job.aggregate_id, for_update=True)
                run.status = "failed"
                run.failure_code = "suggestion_failed"
            self._jobs.fail_attempt(
                job.id,
                "suggestion_failed",
                retryable=True,
                safe_message="Suggestion generation failed safely.",
            )
            raise

    def get(self, suggestion_id: UUID, owner_id: UUID | None = None) -> SuggestionRead:
        with self._session_factory.begin() as session:
            run = self._get_model(session, suggestion_id, owner_id=owner_id, for_update=True)
            if (
                run.expires_at is not None
                and run.expires_at <= utc_now()
                and run.status
                in {
                    "feasible",
                    "infeasible",
                }
            ):
                run.status = "expired"
            return self._read(run)

    def accept(
        self,
        owner_id: UUID,
        suggestion_id: UUID,
        selected_item_ids: tuple[UUID, ...],
        *,
        expected_plan_version: int,
    ) -> MealPlanRead:
        if not selected_item_ids or len(set(selected_item_ids)) != len(selected_item_ids):
            raise DomainError(
                "suggestion_selection_invalid", "Select one or more unique suggestion items.", 422
            )
        now = utc_now()
        with self._session_factory.begin() as session:
            run = self._get_model(session, suggestion_id, owner_id=owner_id, for_update=True)
            owner = session.get(OwnerAccount, owner_id)
            if owner is None:
                raise DomainError("owner_not_found", "Owner account was not found.", 404)
            if run.expires_at is not None and run.expires_at <= now:
                run.status = "expired"
                raise DomainError("suggestion_expired", "This suggestion has expired.", 409)
            if run.status not in {"feasible", "infeasible"}:
                raise DomainError("suggestion_not_ready", "Suggestion is not ready to accept.", 409)
            plan = MealPlanRepository(session).get_week(owner_id, run.week_start, for_update=True)
            require_version(expected_plan_version, plan.version)
            require_version(run.plan_version, plan.version)
            by_id = {item.id: item for item in run.items}
            selected_items = []
            for item_id in selected_item_ids:
                item = by_id.get(item_id)
                if item is None or item.accepted_at is not None or item.recipe_id is None:
                    raise DomainError(
                        "suggestion_item_unavailable",
                        "A selected suggestion item is unavailable.",
                        409,
                    )
                selected_items.append(item)
            for item in selected_items:
                if item.local_date < today_in_timezone(owner.timezone):
                    raise DomainError(
                        "suggestion_date_past",
                        "This suggestion includes a past day. Create a fresh suggestion for today "
                        "or a future day.",
                        409,
                    )
                maximum = session.scalar(
                    select(func.max(MealPlanEntry.position)).where(
                        MealPlanEntry.meal_plan_id == plan.id,
                        MealPlanEntry.local_date == item.local_date,
                        MealPlanEntry.meal_slot == item.meal_slot,
                    )
                )
                snapshot = MealNutritionSnapshot(
                    recipe_id=item.recipe_id,
                    estimate_id=None,
                    basis_servings=item.servings,
                    calories_kcal=item.calories_kcal,
                    protein_g=item.protein_g,
                    carbohydrate_g=item.carbohydrate_g,
                    fat_g=item.fat_g,
                    nutrition_state=item.nutrition_state,
                    coverage_ratio=item.coverage_ratio,
                )
                session.add(snapshot)
                session.flush()
                entry = MealPlanEntry(
                    meal_plan_id=plan.id,
                    local_date=item.local_date,
                    meal_slot=item.meal_slot,
                    position=(maximum if maximum is not None else -1) + 1,
                    recipe_id=item.recipe_id,
                    recipe_title_snapshot=item.recipe_title,
                    servings=item.servings,
                    nutrition_snapshot_id=snapshot.id,
                    origin="suggestion",
                    version=1,
                )
                session.add(entry)
                session.flush()
                item.accepted_at = now
                item.accepted_entry_id = entry.id
            plan.version += 1
            GroceryListService.mark_dirty(session, plan.id)
        return self._plans.get(owner_id, run.week_start)

    @staticmethod
    def _validate(value: SuggestionWrite, owner: OwnerAccount) -> SuggestionWrite:
        if value.scope not in {"meal", "day", "week"}:
            raise DomainError("suggestion_scope_invalid", "Suggestion scope is invalid.", 422)
        if value.scope in {"meal", "day"} and value.local_date is None:
            raise DomainError("suggestion_date_required", "A local date is required.", 422)
        if value.scope == "meal" and not value.meal_slot:
            raise DomainError("suggestion_meal_required", "A meal slot is required.", 422)
        if value.local_date is not None and not (
            value.week_start <= value.local_date <= value.week_start + timedelta(days=6)
        ):
            raise DomainError("suggestion_date_outside_week", "Date is outside the week.", 422)
        if week_start_for(value.week_start, owner.week_starts_on) != value.week_start:
            raise DomainError(
                "suggestion_week_start_invalid",
                "Choose the start of a planning week that matches your account settings.",
                422,
            )
        today = today_in_timezone(owner.timezone)
        if value.local_date is not None and value.local_date < today:
            raise DomainError(
                "suggestion_date_past",
                "Past planning days are read-only. Choose today or a future day.",
                409,
            )
        if value.week_start + timedelta(days=6) < today:
            raise DomainError(
                "suggestion_week_past",
                "This planning week has already passed. Choose today or a future week.",
                409,
            )
        if value.required_recipe_ids & value.excluded_recipe_ids:
            raise DomainError(
                "suggestion_recipe_conflict", "A required recipe cannot also be excluded.", 422
            )
        if not 1 <= value.max_recipe_repetitions <= 21:
            raise DomainError("suggestion_repetition_invalid", "Repetition limit is invalid.", 422)
        tolerances = tuple(
            getattr(value.tolerances, field)
            for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
        )
        if any(item < 0 for item in tolerances):
            raise DomainError("suggestion_tolerance_invalid", "Tolerances cannot be negative.", 422)
        return value

    @staticmethod
    def _ensure_plan(session: Session, owner_id: UUID, week_start: date) -> MealPlan:
        repository = MealPlanRepository(session)
        plan = repository.find_week(owner_id, week_start)
        if plan is not None:
            if plan.goal is None:
                goal = GoalRepository(session).effective(owner_id, week_start)
                plan.goal = goal
            return plan
        owner = session.get(OwnerAccount, owner_id)
        if owner is None:
            raise DomainError("owner_not_found", "Owner account was not found.", 404)
        goal = GoalRepository(session).effective(owner_id, week_start)
        plan = MealPlan(
            owner_id=owner_id,
            week_start=week_start,
            timezone=owner.timezone,
            goal_id=goal.id,
            goal=goal,
            version=1,
        )
        session.add(plan)
        session.flush()
        return plan

    @staticmethod
    def _remaining_target(plan: MealPlan, value: SuggestionWrite) -> SuggestionTarget:
        if plan.goal is None:
            raise DomainError(
                "goal_not_found", "Add a nutrition guide before asking for suggestions.", 404
            )
        goal = plan.goal
        goal_values = SuggestionTarget(
            goal.target_kcal,
            goal.protein_g,
            goal.carbohydrate_g,
            goal.fat_g,
        )
        if value.scope == "meal":
            target = next(
                (item for item in goal.meal_targets if item.meal_slot == value.meal_slot), None
            )
            if target is not None and all(
                getattr(target, field) is not None
                for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
            ):
                goal_values = SuggestionTarget(
                    cast(Decimal, target.calories_kcal),
                    cast(Decimal, target.protein_g),
                    cast(Decimal, target.carbohydrate_g),
                    cast(Decimal, target.fat_g),
                )
        multiplier = Decimal(7) if value.scope == "week" else Decimal(1)
        relevant = [
            entry
            for entry in plan.entries
            if value.scope == "week"
            or (entry.local_date == value.local_date and value.scope == "day")
            or (
                entry.local_date == value.local_date
                and entry.meal_slot == value.meal_slot
                and value.scope == "meal"
            )
        ]
        remaining: list[Decimal] = []
        for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g"):
            current_values = [getattr(entry.nutrition_snapshot, field) for entry in relevant]
            if any(item is None for item in current_values):
                raise DomainError(
                    "suggestion_plan_nutrition_incomplete",
                    "Resolve incomplete planned nutrition before requesting suggestions.",
                    409,
                )
            current = sum((cast(Decimal, item) for item in current_values), Decimal(0))
            remaining.append(
                quantize_decimal(
                    max(getattr(goal_values, field) * multiplier - current, Decimal(0)),
                    NUTRIENT_SCALE,
                )
            )
        return SuggestionTarget(*remaining)

    @staticmethod
    def _input_hash(plan: MealPlan, value: SuggestionWrite, target: SuggestionTarget) -> str:
        payload = {
            "planId": str(plan.id),
            "planVersion": plan.version,
            "scope": value.scope,
            "weekStart": value.week_start.isoformat(),
            "localDate": value.local_date.isoformat() if value.local_date else None,
            "mealSlot": value.meal_slot,
            "target": [
                canonical_decimal(getattr(target, field))
                for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
            ],
            "tolerances": [
                canonical_decimal(getattr(value.tolerances, field))
                for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
            ],
            "excluded": sorted(map(str, value.excluded_recipe_ids)),
            "required": sorted(map(str, value.required_recipe_ids)),
            "maxRepetitions": value.max_recipe_repetitions,
            "solverVersion": SOLVER_VERSION,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _candidate_recipes(self) -> dict[UUID, RecipeRead]:
        page = self._recipes.list(
            query=None,
            nutrition_state=None,
            include_archived=False,
            cursor=None,
            limit=10_000,
        )
        return {
            recipe.id: recipe
            for recipe in page.items
            if recipe.status != "archived"
            and recipe.nutrition_state not in {"stale", "pending", "failed"}
            and recipe.nutrition is not None
            and all(
                getattr(recipe.nutrition.macros, field) is not None
                for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
            )
        }

    @staticmethod
    def _problem(
        run: SuggestionRun, plan: MealPlan, recipes: dict[UUID, RecipeRead]
    ) -> SuggestionProblem:
        candidates = tuple(
            SuggestionCandidate(
                recipe.id,
                recipe.title,
                cast(Decimal, recipe.nutrition.macros.calories_kcal),
                cast(Decimal, recipe.nutrition.macros.protein_g),
                cast(Decimal, recipe.nutrition.macros.carbohydrate_g),
                cast(Decimal, recipe.nutrition.macros.fat_g),
            )
            for recipe in recipes.values()
            if recipe.nutrition is not None
        )
        repetitions: dict[UUID, int] = {}
        for entry in plan.entries:
            if entry.recipe_id is not None:
                repetitions[entry.recipe_id] = repetitions.get(entry.recipe_id, 0) + 1
        return SuggestionProblem(
            candidates=candidates,
            target=SuggestionTarget(
                run.target_calories_kcal,
                run.target_protein_g,
                run.target_carbohydrate_g,
                run.target_fat_g,
            ),
            tolerances=SuggestionTarget(
                run.tolerance_calories_kcal,
                run.tolerance_protein_g,
                run.tolerance_carbohydrate_g,
                run.tolerance_fat_g,
            ),
            excluded_recipe_ids=frozenset(run.excluded_recipe_ids),
            required_recipe_ids=frozenset(run.required_recipe_ids),
            existing_recipe_repetitions=repetitions,
            max_recipe_repetitions=run.max_recipe_repetitions,
            max_entries=7 if run.scope == "week" else 3,
            time_limit_seconds=run.time_limit_seconds,
        )

    @staticmethod
    def _store_solution(
        session: Session,
        run: SuggestionRun,
        plan: MealPlan,
        solution: SuggestionSolution,
        recipes: dict[UUID, RecipeRead],
    ) -> None:
        if plan.goal is None:
            raise DomainError(
                "goal_not_found", "Add a nutrition guide before asking for suggestions.", 404
            )
        goal = plan.goal
        run.items.clear()
        suggested_snapshots: list[PlannedSnapshot] = []
        for position, selection in enumerate(solution.items):
            recipe = recipes[selection.recipe_id]
            assert recipe.nutrition is not None
            if run.local_date:
                local_date = run.local_date
            else:
                today = today_in_timezone(plan.timezone)
                writable_dates = [
                    run.week_start + timedelta(days=index)
                    for index in range(7)
                    if run.week_start + timedelta(days=index) >= today
                ]
                if not writable_dates:
                    raise DomainError(
                        "suggestion_date_past",
                        "There are no writable days left in this planning week.",
                        409,
                    )
                local_date = writable_dates[position % len(writable_dates)]
            meal_slot = run.meal_slot or "suggested"
            snapshot = create_snapshot(
                SnapshotSource(
                    recipe.id,
                    None,
                    recipe.title,
                    recipe.nutrition.macros,
                    cast(NutritionReliability, recipe.nutrition.status),
                    recipe.nutrition.coverage_ratio,
                ),
                selection.servings,
            )
            assert all(
                getattr(snapshot, field) is not None
                for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
            )
            run.items.append(
                SuggestionItem(
                    recipe_id=recipe.id,
                    recipe_title=recipe.title,
                    local_date=local_date,
                    meal_slot=meal_slot,
                    servings=selection.servings,
                    calories_kcal=cast(Decimal, snapshot.calories_kcal),
                    protein_g=cast(Decimal, snapshot.protein_g),
                    carbohydrate_g=cast(Decimal, snapshot.carbohydrate_g),
                    fat_g=cast(Decimal, snapshot.fat_g),
                    nutrition_state=snapshot.status,
                    coverage_ratio=snapshot.coverage_ratio,
                    position=position,
                )
            )
            suggested_snapshots.append(PlannedSnapshot(local_date, meal_slot, position, snapshot))
        existing = [
            PlannedSnapshot(
                entry.local_date,
                entry.meal_slot,
                entry.position,
                MealPlanService._snapshot_value(entry.nutrition_snapshot),
            )
            for entry in plan.entries
        ]
        totals = aggregate_plan(
            existing + suggested_snapshots,
            MacroValues(
                goal.target_kcal,
                goal.protein_g,
                goal.carbohydrate_g,
                goal.fat_g,
            ),
        )
        run.projected_day_totals = {
            day.isoformat(): SuggestionService._total_json(total)
            for day, total in totals.day_totals.items()
        }
        run.projected_week_total = SuggestionService._total_json(totals.week_total)
        run.status = solution.status
        run.unmet_constraint_count = solution.unmet_constraint_count
        run.objective_score = solution.objective_score
        run.distance_calories = solution.distance_components.calories
        run.distance_protein = solution.distance_components.protein
        run.distance_carbohydrates = solution.distance_components.carbohydrates
        run.distance_fat = solution.distance_components.fat
        run.repetition_overage = solution.distance_components.repetition_overage
        run.missing_required_recipes = solution.distance_components.missing_required_recipes
        run.missed_constraints = list(solution.missed_constraints)
        run.ordered_recipe_ids = [item.recipe_id for item in solution.items]
        run.failure_code = None
        session.flush()

    @staticmethod
    def _total_json(total: PeriodTotal) -> dict[str, object]:
        return {
            "caloriesKcal": canonical_decimal(cast(Decimal, total.calories_kcal)),
            "proteinG": canonical_decimal(cast(Decimal, total.protein_g)),
            "carbohydrateG": canonical_decimal(cast(Decimal, total.carbohydrate_g)),
            "fatG": canonical_decimal(cast(Decimal, total.fat_g)),
            "status": total.status,
            "coverageRatio": canonical_decimal(total.coverage_ratio),
        }

    @staticmethod
    def _get_model(
        session: Session,
        suggestion_id: UUID,
        *,
        owner_id: UUID | None = None,
        for_update: bool = False,
    ) -> SuggestionRun:
        statement = (
            select(SuggestionRun)
            .where(SuggestionRun.id == suggestion_id)
            .options(selectinload(SuggestionRun.items))
        )
        if owner_id is not None:
            statement = statement.where(SuggestionRun.owner_id == owner_id)
        if for_update:
            statement = statement.with_for_update()
        run = session.scalar(statement)
        if run is None:
            raise DomainError("suggestion_not_found", "Suggestion was not found.", 404)
        return run

    @staticmethod
    def _read(run: SuggestionRun) -> SuggestionRead:
        distance: dict[str, Decimal | int] | None = None
        if run.distance_calories is not None:
            distance = {
                "calories": run.distance_calories,
                "protein": cast(Decimal, run.distance_protein),
                "carbohydrates": cast(Decimal, run.distance_carbohydrates),
                "fat": cast(Decimal, run.distance_fat),
                "repetitionOverage": cast(int, run.repetition_overage),
                "missingRequiredRecipes": cast(int, run.missing_required_recipes),
            }
        return SuggestionRead(
            run.id,
            run.status,
            SuggestionWrite(
                run.scope,
                run.week_start,
                run.local_date,
                run.meal_slot,
                SuggestionTarget(
                    run.tolerance_calories_kcal,
                    run.tolerance_protein_g,
                    run.tolerance_carbohydrate_g,
                    run.tolerance_fat_g,
                ),
                frozenset(run.excluded_recipe_ids),
                frozenset(run.required_recipe_ids),
                run.max_recipe_repetitions,
            ),
            SuggestionTarget(
                run.target_calories_kcal,
                run.target_protein_g,
                run.target_carbohydrate_g,
                run.target_fat_g,
            ),
            tuple(
                SuggestionItemRead(
                    item.id,
                    item.recipe_id,
                    item.recipe_title,
                    item.local_date,
                    item.meal_slot,
                    item.servings,
                    item.calories_kcal,
                    item.protein_g,
                    item.carbohydrate_g,
                    item.fat_g,
                    item.nutrition_state,
                    item.coverage_ratio,
                    item.accepted_at is not None,
                )
                for item in sorted(run.items, key=lambda item: item.position)
            ),
            run.projected_day_totals,
            run.projected_week_total,
            tuple(run.missed_constraints),
            run.unmet_constraint_count,
            run.objective_score,
            distance,
            run.plan_version,
            run.failure_code,
            run.created_at,
            run.expires_at,
        )
