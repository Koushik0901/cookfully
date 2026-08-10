from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from vigor_vine.api.schemas.plans import (
    MealPlanResponse,
    PeriodTotalResponse,
    UserGoalResponse,
)
from vigor_vine.api.schemas.recipes import RecipePageResponse
from vigor_vine.application.meal_plans import GoalService, MealPlanService
from vigor_vine.application.recipe_queries import RecipeQueryService
from vigor_vine.domain.common import DomainError


def parse_date(value: str, *, code: str = "invalid_date") -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DomainError(code, "Date must use YYYY-MM-DD format.", 422) from exc


class ReadTools:
    def __init__(
        self,
        goals: GoalService,
        plans: MealPlanService,
        recipes: RecipeQueryService,
    ) -> None:
        self._goals = goals
        self._plans = plans
        self._recipes = recipes

    def get_current_goals(self, owner_id: UUID, *, on_date: str | None = None) -> dict[str, Any]:
        effective_on = parse_date(on_date) if on_date is not None else datetime.now(UTC).date()
        return UserGoalResponse.from_read(self._goals.get(owner_id, effective_on)).model_dump(
            mode="json", by_alias=True
        )

    def get_meal_plan(self, owner_id: UUID, *, week_start: str) -> dict[str, Any]:
        plan = self._plans.get(owner_id, parse_date(week_start, code="invalid_week_boundary"))
        return MealPlanResponse.from_read(plan).model_dump(mode="json", by_alias=True)

    def get_period_totals(
        self,
        owner_id: UUID,
        *,
        week_start: str,
        local_date: str | None = None,
        meal_slot: str | None = None,
    ) -> dict[str, Any]:
        parsed_week = parse_date(week_start, code="invalid_week_boundary")
        parsed_local = parse_date(local_date) if local_date is not None else None
        if meal_slot is not None and parsed_local is None:
            raise DomainError("invalid_constraint", "meal_slot requires local_date.", 422)
        plan = self._plans.get(owner_id, parsed_week)
        if parsed_local is not None and not parsed_week <= parsed_local <= parsed_week + timedelta(
            days=6
        ):
            raise DomainError(
                "date_outside_week", "Date is outside the requested meal-plan week.", 422
            )
        total = None
        if parsed_local is None:
            total = plan.totals.week_total
            entries = plan.entries
        elif meal_slot is None:
            total = plan.totals.day_totals.get(parsed_local)
            entries = tuple(item for item in plan.entries if item.local_date == parsed_local)
        else:
            total = plan.totals.meal_totals.get((parsed_local, meal_slot))
            entries = tuple(
                item
                for item in plan.entries
                if item.local_date == parsed_local and item.meal_slot == meal_slot
            )
        if total is None:
            raise DomainError("period_not_found", "No entries exist for that period.", 404)
        return {
            "weekStart": parsed_week.isoformat(),
            "localDate": parsed_local.isoformat() if parsed_local is not None else None,
            "mealSlot": meal_slot,
            "total": PeriodTotalResponse.from_total(total).model_dump(mode="json", by_alias=True),
            "entryIds": [str(item.id) for item in entries],
        }

    def find_recipes(
        self,
        owner_id: UUID,
        *,
        query: str | None = None,
        calories_min: str | None = None,
        calories_max: str | None = None,
        protein_min: str | None = None,
        protein_max: str | None = None,
        carbohydrate_min: str | None = None,
        carbohydrate_max: str | None = None,
        fat_min: str | None = None,
        fat_max: str | None = None,
        nutrition_state: str | None = None,
        include_archived: bool = False,
        cursor: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        del owner_id  # Recipes are instance-owned in the single-owner data model.
        if not 1 <= limit <= 100:
            raise DomainError("invalid_constraint", "limit must be between 1 and 100.", 422)
        page = self._recipes.list(
            query=query,
            nutrition_state=nutrition_state,
            include_archived=include_archived,
            cursor=cursor,
            limit=limit,
        )
        bounds = {
            "calories_kcal": self._bounds(calories_min, calories_max),
            "protein_g": self._bounds(protein_min, protein_max),
            "carbohydrate_g": self._bounds(carbohydrate_min, carbohydrate_max),
            "fat_g": self._bounds(fat_min, fat_max),
        }
        filtered = tuple(
            recipe
            for recipe in page.items
            if recipe.nutrition is not None
            and all(
                self._inside(getattr(recipe.nutrition.macros, field), minimum, maximum)
                for field, (minimum, maximum) in bounds.items()
            )
        )
        if all(minimum is None and maximum is None for minimum, maximum in bounds.values()):
            filtered = page.items
        response = RecipePageResponse.from_read(type(page)(filtered, page.next_cursor))
        return response.model_dump(mode="json", by_alias=True)

    @staticmethod
    def _bounds(minimum: str | None, maximum: str | None) -> tuple[Decimal | None, Decimal | None]:
        pattern = r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,6})?"
        if (minimum is not None and re.fullmatch(pattern, minimum) is None) or (
            maximum is not None and re.fullmatch(pattern, maximum) is None
        ):
            raise DomainError(
                "invalid_constraint", "Nutrition bounds must be decimal strings.", 422
            )
        lower = Decimal(minimum) if minimum is not None else None
        upper = Decimal(maximum) if maximum is not None else None
        if (lower is not None and lower < 0) or (upper is not None and upper < 0):
            raise DomainError("invalid_constraint", "Nutrition bounds cannot be negative.", 422)
        if lower is not None and upper is not None and lower > upper:
            raise DomainError("invalid_constraint", "Minimum cannot exceed maximum.", 422)
        return lower, upper

    @staticmethod
    def _inside(value: Decimal | None, minimum: Decimal | None, maximum: Decimal | None) -> bool:
        return (
            value is not None
            and (minimum is None or value >= minimum)
            and (maximum is None or value <= maximum)
        )
