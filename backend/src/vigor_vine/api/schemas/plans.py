from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import ConfigDict, Field

from vigor_vine.api.schemas.recipes import ApiModel, Decimal6, ServingDecimal
from vigor_vine.application.meal_plans import (
    GoalRead,
    GoalWrite,
    MealPlanEntryRead,
    MealPlanEntryWrite,
    MealPlanRead,
    MealTargetWrite,
)
from vigor_vine.domain.common import canonical_decimal, display_calories, display_macro
from vigor_vine.domain.plan_totals import PeriodTotal


class MealTargetRequest(ApiModel):
    meal_slot: str = Field(alias="mealSlot", min_length=1, max_length=80)
    calories_kcal: Decimal6 | None = Field(alias="caloriesKcal", default=None)
    protein_g: Decimal6 | None = Field(alias="proteinG", default=None)
    carbohydrate_g: Decimal6 | None = Field(alias="carbohydrateG", default=None)
    fat_g: Decimal6 | None = Field(alias="fatG", default=None)

    def to_write(self) -> MealTargetWrite:
        return MealTargetWrite(
            self.meal_slot,
            self.calories_kcal,
            self.protein_g,
            self.carbohydrate_g,
            self.fat_g,
        )


class UserGoalWriteRequest(ApiModel):
    mode: str
    maintenance_kcal: Decimal6 = Field(alias="maintenanceKcal")
    calories_kcal: Decimal6 = Field(alias="caloriesKcal")
    protein_g: Decimal6 = Field(alias="proteinG")
    carbohydrate_g: Decimal6 = Field(alias="carbohydrateG")
    fat_g: Decimal6 = Field(alias="fatG")
    effective_from: date = Field(alias="effectiveFrom")
    effective_to: date | None = Field(alias="effectiveTo", default=None)
    meal_targets: tuple[MealTargetRequest, ...] = Field(alias="mealTargets", default=())

    def to_write(self) -> GoalWrite:
        return GoalWrite(
            self.mode,
            self.maintenance_kcal,
            self.calories_kcal,
            self.protein_g,
            self.carbohydrate_g,
            self.fat_g,
            self.effective_from,
            self.effective_to,
            tuple(item.to_write() for item in self.meal_targets),
        )


class MealTargetResponse(MealTargetRequest):
    @classmethod
    def from_read(cls, value: MealTargetWrite) -> MealTargetResponse:
        return cls(
            meal_slot=value.meal_slot,
            calories_kcal=value.calories_kcal,
            protein_g=value.protein_g,
            carbohydrate_g=value.carbohydrate_g,
            fat_g=value.fat_g,
        )


class UserGoalResponse(ApiModel):
    id: UUID
    mode: str
    maintenance_kcal: Decimal6 = Field(alias="maintenanceKcal")
    calories_kcal: Decimal6 = Field(alias="caloriesKcal")
    protein_g: Decimal6 = Field(alias="proteinG")
    carbohydrate_g: Decimal6 = Field(alias="carbohydrateG")
    fat_g: Decimal6 = Field(alias="fatG")
    effective_from: date = Field(alias="effectiveFrom")
    effective_to: date | None = Field(alias="effectiveTo", default=None)
    meal_targets: tuple[MealTargetResponse, ...] = Field(alias="mealTargets", default=())
    macro_calorie_difference: str | None = Field(
        alias="macroCalorieDifference",
        default=None,
        pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]{1,6})?$",
    )
    version: int = Field(ge=1)

    @classmethod
    def from_read(cls, value: GoalRead) -> UserGoalResponse:
        return cls(
            id=value.id,
            mode=value.mode,
            maintenance_kcal=value.maintenance_kcal,
            calories_kcal=value.target_kcal,
            protein_g=value.protein_g,
            carbohydrate_g=value.carbohydrate_g,
            fat_g=value.fat_g,
            effective_from=value.effective_from,
            effective_to=value.effective_to,
            meal_targets=tuple(MealTargetResponse.from_read(item) for item in value.meal_targets),
            macro_calorie_difference=(
                canonical_decimal(value.macro_calorie_difference)
                if value.macro_calorie_difference is not None
                else None
            ),
            version=value.version,
        )


class MealPlanEntryWriteRequest(ApiModel):
    local_date: date = Field(alias="localDate")
    meal_slot: str = Field(alias="mealSlot", min_length=1, max_length=80)
    recipe_id: UUID = Field(alias="recipeId")
    servings: ServingDecimal
    position: int | None = Field(default=None, ge=0)
    refresh_nutrition: bool = Field(alias="refreshNutrition", default=False)

    def to_write(self) -> MealPlanEntryWrite:
        return MealPlanEntryWrite(
            self.local_date,
            self.meal_slot,
            self.recipe_id,
            self.servings,
            self.position,
            self.refresh_nutrition,
        )


class NutritionSnapshotResponse(ApiModel):
    basis_servings: str = Field(alias="basisServings")
    calories_kcal: str | None = Field(alias="caloriesKcal")
    protein_g: str | None = Field(alias="proteinG")
    carbohydrate_g: str | None = Field(alias="carbohydrateG")
    fat_g: str | None = Field(alias="fatG")
    status: str
    coverage_ratio: str = Field(alias="coverageRatio")

    @classmethod
    def from_read(cls, value: MealPlanEntryRead) -> NutritionSnapshotResponse:
        nutrition = value.nutrition
        return cls(
            basis_servings=canonical_decimal(nutrition.basis_servings, places=3),
            calories_kcal=(
                display_calories(nutrition.calories_kcal)
                if nutrition.calories_kcal is not None
                else None
            ),
            protein_g=display_macro(nutrition.protein_g)
            if nutrition.protein_g is not None
            else None,
            carbohydrate_g=(
                display_macro(nutrition.carbohydrate_g)
                if nutrition.carbohydrate_g is not None
                else None
            ),
            fat_g=display_macro(nutrition.fat_g) if nutrition.fat_g is not None else None,
            status=nutrition.status,
            coverage_ratio=canonical_decimal(nutrition.coverage_ratio),
        )


class MealPlanEntryResponse(ApiModel):
    id: UUID
    local_date: date = Field(alias="localDate")
    meal_slot: str = Field(alias="mealSlot")
    recipe_id: UUID | None = Field(alias="recipeId")
    recipe_title: str = Field(alias="recipeTitle")
    servings: str
    position: int
    refresh_nutrition: bool = Field(alias="refreshNutrition", default=False)
    nutrition: NutritionSnapshotResponse
    origin: str
    version: int

    @classmethod
    def from_read(cls, value: MealPlanEntryRead) -> MealPlanEntryResponse:
        return cls(
            id=value.id,
            local_date=value.local_date,
            meal_slot=value.meal_slot,
            recipe_id=value.recipe_id,
            recipe_title=value.recipe_title,
            servings=canonical_decimal(value.servings, places=3),
            position=value.position,
            refresh_nutrition=False,
            nutrition=NutritionSnapshotResponse.from_read(value),
            origin=value.origin,
            version=value.version,
        )


class SignedMacroResponse(ApiModel):
    calories_kcal: str | None = Field(alias="caloriesKcal")
    protein_g: str | None = Field(alias="proteinG")
    carbohydrate_g: str | None = Field(alias="carbohydrateG")
    fat_g: str | None = Field(alias="fatG")


class PeriodTotalResponse(ApiModel):
    calories_kcal: str | None = Field(alias="caloriesKcal")
    protein_g: str | None = Field(alias="proteinG")
    carbohydrate_g: str | None = Field(alias="carbohydrateG")
    fat_g: str | None = Field(alias="fatG")
    status: str
    coverage_ratio: str = Field(alias="coverageRatio")
    target_difference: SignedMacroResponse | None = Field(alias="targetDifference", default=None)

    @classmethod
    def from_total(cls, value: PeriodTotal) -> PeriodTotalResponse:
        displayed = value.as_strings()
        difference = (
            value.target_difference_strings() if value.target_difference is not None else None
        )
        return cls(
            calories_kcal=displayed["caloriesKcal"],
            protein_g=displayed["proteinG"],
            carbohydrate_g=displayed["carbohydrateG"],
            fat_g=displayed["fatG"],
            status=value.status,
            coverage_ratio=canonical_decimal(value.coverage_ratio),
            target_difference=(
                SignedMacroResponse(
                    calories_kcal=difference["caloriesKcal"],
                    protein_g=difference["proteinG"],
                    carbohydrate_g=difference["carbohydrateG"],
                    fat_g=difference["fatG"],
                )
                if difference is not None
                else None
            ),
        )


class MealPlanResponse(ApiModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: UUID
    week_start: date = Field(alias="weekStart")
    timezone: str
    goal: UserGoalResponse
    entries: tuple[MealPlanEntryResponse, ...]
    day_totals: dict[str, PeriodTotalResponse] = Field(alias="dayTotals")
    week_total: PeriodTotalResponse = Field(alias="weekTotal")
    grocery_status: str = Field(alias="groceryStatus", default="absent")
    version: int

    @classmethod
    def from_read(cls, value: MealPlanRead) -> MealPlanResponse:
        return cls(
            id=value.id,
            week_start=value.week_start,
            timezone=value.timezone,
            goal=UserGoalResponse.from_read(value.goal),
            entries=tuple(MealPlanEntryResponse.from_read(item) for item in value.entries),
            day_totals={
                day.isoformat(): PeriodTotalResponse.from_total(total)
                for day, total in value.totals.day_totals.items()
            },
            week_total=PeriodTotalResponse.from_total(value.totals.week_total),
            grocery_status=value.grocery_status,
            version=value.version,
        )
