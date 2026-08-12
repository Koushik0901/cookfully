from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from cookfully.api.schemas.recipes import ApiModel, Decimal6
from cookfully.application.suggestions import (
    SuggestionItemRead,
    SuggestionRead,
    SuggestionWrite,
)
from cookfully.domain.common import canonical_decimal, display_calories, display_macro
from cookfully.domain.suggestion_solver import SuggestionTarget


class SuggestionMacroValues(ApiModel):
    calories_kcal: Decimal6 = Field(alias="caloriesKcal", ge=0)
    protein_g: Decimal6 = Field(alias="proteinG", ge=0)
    carbohydrate_g: Decimal6 = Field(alias="carbohydrateG", ge=0)
    fat_g: Decimal6 = Field(alias="fatG", ge=0)

    def to_target(self) -> SuggestionTarget:
        return SuggestionTarget(self.calories_kcal, self.protein_g, self.carbohydrate_g, self.fat_g)

    @classmethod
    def from_target(cls, value: SuggestionTarget) -> SuggestionMacroValues:
        return cls(
            calories_kcal=value.calories_kcal,
            protein_g=value.protein_g,
            carbohydrate_g=value.carbohydrate_g,
            fat_g=value.fat_g,
        )


class SuggestionRequest(ApiModel):
    scope: str
    week_start: date = Field(alias="weekStart")
    local_date: date | None = Field(alias="localDate", default=None)
    meal_slot: str | None = Field(alias="mealSlot", default=None, max_length=80)
    tolerances: SuggestionMacroValues
    excluded_recipe_ids: tuple[UUID, ...] = Field(alias="excludedRecipeIds", default=())
    required_recipe_ids: tuple[UUID, ...] = Field(alias="requiredRecipeIds", default=())
    max_recipe_repetitions: int = Field(alias="maxRecipeRepetitions", default=3, ge=1, le=21)

    @model_validator(mode="after")
    def validate_scope_fields(self) -> SuggestionRequest:
        if self.scope not in {"meal", "day", "week"}:
            raise ValueError("scope must be meal, day, or week")
        if self.scope in {"meal", "day"} and self.local_date is None:
            raise ValueError("localDate is required for meal and day suggestions")
        if self.scope == "meal" and not self.meal_slot:
            raise ValueError("mealSlot is required for meal suggestions")
        return self

    def to_write(self) -> SuggestionWrite:
        return SuggestionWrite(
            self.scope,
            self.week_start,
            self.local_date,
            self.meal_slot,
            self.tolerances.to_target(),
            frozenset(self.excluded_recipe_ids),
            frozenset(self.required_recipe_ids),
            self.max_recipe_repetitions,
        )

    @classmethod
    def from_write(cls, value: SuggestionWrite) -> SuggestionRequest:
        return cls(
            scope=value.scope,
            week_start=value.week_start,
            local_date=value.local_date,
            meal_slot=value.meal_slot,
            tolerances=SuggestionMacroValues.from_target(value.tolerances),
            excluded_recipe_ids=tuple(sorted(value.excluded_recipe_ids, key=str)),
            required_recipe_ids=tuple(sorted(value.required_recipe_ids, key=str)),
            max_recipe_repetitions=value.max_recipe_repetitions,
        )


class SuggestedNutrition(ApiModel):
    basis_servings: str = Field(alias="basisServings")
    calories_kcal: str = Field(alias="caloriesKcal")
    protein_g: str = Field(alias="proteinG")
    carbohydrate_g: str = Field(alias="carbohydrateG")
    fat_g: str = Field(alias="fatG")
    status: str
    coverage_ratio: str = Field(alias="coverageRatio")


class SuggestionItemResponse(ApiModel):
    id: UUID
    recipe_id: UUID | None = Field(alias="recipeId")
    recipe_title: str = Field(alias="recipeTitle")
    local_date: date = Field(alias="localDate")
    meal_slot: str = Field(alias="mealSlot")
    servings: str
    projected_nutrition: SuggestedNutrition = Field(alias="projectedNutrition")
    accepted: bool

    @classmethod
    def from_read(cls, value: SuggestionItemRead) -> SuggestionItemResponse:
        return cls(
            id=value.id,
            recipe_id=value.recipe_id,
            recipe_title=value.recipe_title,
            local_date=value.local_date,
            meal_slot=value.meal_slot,
            servings=canonical_decimal(value.servings, places=3),
            projected_nutrition=SuggestedNutrition(
                basis_servings=canonical_decimal(value.servings, places=3),
                calories_kcal=display_calories(value.calories_kcal),
                protein_g=display_macro(value.protein_g),
                carbohydrate_g=display_macro(value.carbohydrate_g),
                fat_g=display_macro(value.fat_g),
                status=value.nutrition_state,
                coverage_ratio=canonical_decimal(value.coverage_ratio),
            ),
            accepted=value.accepted,
        )


class SuggestionDistanceResponse(ApiModel):
    calories: str
    protein: str
    carbohydrates: str
    fat: str
    repetition_overage: int = Field(alias="repetitionOverage")
    missing_required_recipes: int = Field(alias="missingRequiredRecipes")


class SuggestionResultResponse(ApiModel):
    id: UUID
    status: str
    request: SuggestionRequest
    target: SuggestionMacroValues
    items: tuple[SuggestionItemResponse, ...]
    projected_day_totals: dict[str, object] = Field(alias="projectedDayTotals")
    projected_week_total: dict[str, object] | None = Field(alias="projectedWeekTotal")
    missed_constraints: tuple[str, ...] = Field(alias="missedConstraints")
    unmet_constraint_count: int | None = Field(alias="unmetConstraintCount")
    objective_score: str | None = Field(alias="objectiveScore")
    distance_components: SuggestionDistanceResponse | None = Field(alias="distanceComponents")
    plan_version: int = Field(alias="planVersion", ge=1)
    failure_code: str | None = Field(alias="failureCode")
    ranking: str = "fewest-unmet,weighted-4-3-1-1-2-5,fewer-entries,ordered-recipe-ids"
    planning_notice: str = Field(
        alias="planningNotice", default="Planning aid only—not medical advice."
    )
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime | None = Field(alias="expiresAt")

    @classmethod
    def from_read(cls, value: SuggestionRead) -> SuggestionResultResponse:
        distance = value.distance_components
        return cls(
            id=value.id,
            status=value.status,
            request=SuggestionRequest.from_write(value.request),
            target=SuggestionMacroValues.from_target(value.target),
            items=tuple(SuggestionItemResponse.from_read(item) for item in value.items),
            projected_day_totals=value.projected_day_totals,
            projected_week_total=value.projected_week_total,
            missed_constraints=value.missed_constraints,
            unmet_constraint_count=value.unmet_constraint_count,
            objective_score=(
                canonical_decimal(value.objective_score)
                if value.objective_score is not None
                else None
            ),
            distance_components=(
                SuggestionDistanceResponse(
                    calories=canonical_decimal(cast_decimal(distance["calories"])),
                    protein=canonical_decimal(cast_decimal(distance["protein"])),
                    carbohydrates=canonical_decimal(cast_decimal(distance["carbohydrates"])),
                    fat=canonical_decimal(cast_decimal(distance["fat"])),
                    repetition_overage=int(distance["repetitionOverage"]),
                    missing_required_recipes=int(distance["missingRequiredRecipes"]),
                )
                if distance is not None
                else None
            ),
            plan_version=value.plan_version,
            failure_code=value.failure_code,
            created_at=value.created_at,
            expires_at=value.expires_at,
        )


def cast_decimal(value: Decimal | int) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value)


class SuggestionAcceptanceRequest(ApiModel):
    selected_item_ids: tuple[UUID, ...] = Field(alias="selectedItemIds", min_length=1)
    expected_plan_version: int = Field(alias="expectedPlanVersion", ge=1)
