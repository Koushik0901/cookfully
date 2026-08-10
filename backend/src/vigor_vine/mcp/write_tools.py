from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from vigor_vine.api.schemas.grocery import GroceryListResponse
from vigor_vine.api.schemas.plans import (
    MealPlanEntryResponse,
    MealPlanEntryWriteRequest,
    MealPlanResponse,
)
from vigor_vine.application.grocery_lists import GroceryListService
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.application.meal_plans import MealPlanService
from vigor_vine.domain.common import DomainError
from vigor_vine.mcp.read_tools import parse_date


class WriteTools:
    def __init__(
        self,
        plans: MealPlanService,
        grocery: GroceryListService,
        idempotency: IdempotencyService,
    ) -> None:
        self._plans = plans
        self._grocery = grocery
        self._idempotency = idempotency

    def add_recipe_to_plan(
        self,
        owner_id: UUID,
        *,
        recipe_id: str,
        week_start: str,
        local_date: str,
        meal_slot: str,
        servings: str,
        idempotency_key: str,
        expected_plan_version: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "recipeId": recipe_id,
            "weekStart": week_start,
            "localDate": local_date,
            "mealSlot": meal_slot,
            "servings": servings,
            "expectedPlanVersion": expected_plan_version,
        }

        def mutate() -> dict[str, Any]:
            parsed_week = parse_date(week_start, code="invalid_week_boundary")
            if expected_plan_version is not None:
                self._require_plan_version(owner_id, parsed_week, expected_plan_version)
            value = MealPlanEntryWriteRequest.model_validate(
                {
                    "recipeId": recipe_id,
                    "localDate": local_date,
                    "mealSlot": meal_slot,
                    "servings": servings,
                    "refreshNutrition": False,
                }
            ).to_write()
            entry = self._plans.add(owner_id, parsed_week, value, origin="external")
            plan = self._plans.get(owner_id, parsed_week)
            return self._entry_result(entry, plan, value.local_date)

        return self._idempotent(owner_id, idempotency_key, "mcp.plan.add", payload, mutate)

    def update_meal_plan_entry(
        self,
        owner_id: UUID,
        *,
        entry_id: str,
        local_date: str,
        meal_slot: str,
        servings: str,
        expected_version: int,
        idempotency_key: str,
        refresh_nutrition: bool = False,
        recipe_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "entryId": entry_id,
            "localDate": local_date,
            "mealSlot": meal_slot,
            "servings": servings,
            "expectedVersion": expected_version,
            "refreshNutrition": refresh_nutrition,
        }

        def mutate() -> dict[str, Any]:
            parsed_id = self._uuid(entry_id, "entry_id")
            current = self._plans.get_entry(owner_id, parsed_id)
            selected_recipe = (
                self._uuid(recipe_id, "recipe_id")
                if recipe_id is not None
                else current.entry.recipe_id
            )
            if selected_recipe is None:
                raise DomainError(
                    "recipe_not_found", "The planned recipe is no longer available.", 404
                )
            value = MealPlanEntryWriteRequest.model_validate(
                {
                    "recipeId": str(selected_recipe),
                    "localDate": local_date,
                    "mealSlot": meal_slot,
                    "servings": servings,
                    "position": current.entry.position,
                    "refreshNutrition": refresh_nutrition,
                }
            ).to_write()
            entry = self._plans.update(
                owner_id, parsed_id, value, expected_version=expected_version
            )
            plan = self._plans.get(owner_id, current.week_start)
            return self._entry_result(entry, plan, value.local_date)

        return self._idempotent(owner_id, idempotency_key, "mcp.plan.update", payload, mutate)

    def remove_meal_plan_entry(
        self,
        owner_id: UUID,
        *,
        entry_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = {"entryId": entry_id, "expectedVersion": expected_version}

        def mutate() -> dict[str, Any]:
            parsed_id = self._uuid(entry_id, "entry_id")
            current = self._plans.get_entry(owner_id, parsed_id)
            self._plans.remove(owner_id, parsed_id, expected_version=expected_version)
            plan = self._plans.get(owner_id, current.week_start)
            serialized = MealPlanResponse.from_read(plan).model_dump(mode="json", by_alias=True)
            return {
                "removed": True,
                "entryId": entry_id,
                "weekTotal": serialized["weekTotal"],
                "groceryStatus": serialized["groceryStatus"],
                "planVersion": serialized["version"],
            }

        return self._idempotent(owner_id, idempotency_key, "mcp.plan.remove", payload, mutate)

    def get_grocery_list(self, owner_id: UUID, *, week_start: str) -> dict[str, Any]:
        value = self._grocery.get(owner_id, parse_date(week_start, code="invalid_week_boundary"))
        return GroceryListResponse.from_read(value).model_dump(mode="json", by_alias=True)

    def regenerate_grocery_list(
        self,
        owner_id: UUID,
        *,
        week_start: str,
        idempotency_key: str,
        expected_plan_version: int | None = None,
        expected_list_version: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "weekStart": week_start,
            "expectedPlanVersion": expected_plan_version,
            "expectedListVersion": expected_list_version,
        }

        def mutate() -> dict[str, Any]:
            parsed_week = parse_date(week_start, code="invalid_week_boundary")
            if expected_plan_version is not None:
                self._require_plan_version(owner_id, parsed_week, expected_plan_version)
            if expected_list_version is not None:
                current = self._grocery.get(owner_id, parsed_week)
                if current.version != expected_list_version:
                    raise DomainError(
                        "version_conflict", "The grocery list changed; reload and retry.", 409
                    )
            value = self._grocery.generate(owner_id, parsed_week)
            return GroceryListResponse.from_read(value).model_dump(mode="json", by_alias=True)

        return self._idempotent(
            owner_id, idempotency_key, "mcp.grocery.regenerate", payload, mutate
        )

    def _idempotent(
        self,
        owner_id: UUID,
        key: str,
        operation: str,
        payload: dict[str, Any],
        mutation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if not 16 <= len(key) <= 128:
            raise DomainError(
                "idempotency_key_invalid",
                "Idempotency key must contain between 16 and 128 characters.",
                422,
            )
        decision = self._idempotency.begin(
            owner_id=owner_id, key=key, operation=operation, payload=payload
        )
        if decision.replay:
            if decision.response_body is None:
                raise DomainError(
                    "idempotency_response_missing", "Stored response is unavailable.", 500
                )
            return decision.response_body
        try:
            response = mutation()
        except Exception:
            self._idempotency.abort(owner_id=owner_id, key=key)
            raise
        self._idempotency.complete(
            owner_id=owner_id, key=key, response_status=200, response_body=response
        )
        return response

    def _require_plan_version(
        self, owner_id: UUID, week_start: date, expected_version: int
    ) -> None:
        current = self._plans.get(owner_id, week_start)
        if current.version != expected_version:
            raise DomainError("version_conflict", "The meal plan changed; reload and retry.", 409)

    @staticmethod
    def _entry_result(entry: Any, plan: Any, local_date: date) -> dict[str, Any]:
        serialized = MealPlanResponse.from_read(plan).model_dump(mode="json", by_alias=True)
        return {
            "entry": MealPlanEntryResponse.from_read(entry).model_dump(mode="json", by_alias=True),
            "dayTotal": serialized["dayTotals"][local_date.isoformat()],
            "weekTotal": serialized["weekTotal"],
            "groceryStatus": serialized["groceryStatus"],
            "planVersion": serialized["version"],
        }

    @staticmethod
    def _uuid(value: str, field: str) -> UUID:
        try:
            return UUID(value)
        except ValueError as exc:
            raise DomainError("invalid_identifier", f"{field} must be a UUID.", 422) from exc
