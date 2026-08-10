from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import cast

from vigor_vine.domain.common import display_calories, display_macro
from vigor_vine.domain.meal_snapshots import MealNutritionSnapshotValue, NutritionReliability
from vigor_vine.domain.nutrition import MacroValues

FIELDS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
RELIABILITY = {"partial": 0, "estimated": 1, "source_provided": 2, "manual": 3}


@dataclass(frozen=True, slots=True)
class PlannedSnapshot:
    local_date: date
    meal_slot: str
    position: int
    nutrition: MealNutritionSnapshotValue


@dataclass(frozen=True, slots=True)
class PeriodTotal:
    calories_kcal: Decimal | None
    protein_g: Decimal | None
    carbohydrate_g: Decimal | None
    fat_g: Decimal | None
    status: NutritionReliability
    coverage_ratio: Decimal
    target_difference: MacroValues | None = None

    def as_strings(self) -> dict[str, str | None]:
        return {
            "caloriesKcal": display_calories(self.calories_kcal)
            if self.calories_kcal is not None
            else None,
            "proteinG": display_macro(self.protein_g) if self.protein_g is not None else None,
            "carbohydrateG": display_macro(self.carbohydrate_g)
            if self.carbohydrate_g is not None
            else None,
            "fatG": display_macro(self.fat_g) if self.fat_g is not None else None,
        }

    def target_difference_strings(self) -> dict[str, str | None]:
        values = self.target_difference or MacroValues(None, None, None, None)
        return {
            "caloriesKcal": display_calories(values.calories_kcal)
            if values.calories_kcal is not None
            else None,
            "proteinG": display_macro(values.protein_g) if values.protein_g is not None else None,
            "carbohydrateG": display_macro(values.carbohydrate_g)
            if values.carbohydrate_g is not None
            else None,
            "fatG": display_macro(values.fat_g) if values.fat_g is not None else None,
        }


@dataclass(frozen=True, slots=True)
class PlanTotals:
    meal_totals: dict[tuple[date, str], PeriodTotal]
    day_totals: dict[date, PeriodTotal]
    week_total: PeriodTotal


def _total(
    values: list[MealNutritionSnapshotValue], target: MacroValues | None = None
) -> PeriodTotal:
    def sum_field(field: str) -> Decimal | None:
        items = [getattr(value, field) for value in values]
        if any(item is None for item in items):
            return None
        return sum((item for item in items if item is not None), Decimal(0))

    totals = {field: sum_field(field) for field in FIELDS}
    status = cast(
        NutritionReliability,
        min((value.status for value in values), key=RELIABILITY.__getitem__, default="partial"),
    )
    coverage = min((value.coverage_ratio for value in values), default=Decimal(0))
    difference = None
    if target is not None:
        difference = MacroValues(
            *(
                totals[field] - getattr(target, field)
                if totals[field] is not None and getattr(target, field) is not None
                else None
                for field in FIELDS
            )
        )
    return PeriodTotal(
        **totals, status=status, coverage_ratio=coverage, target_difference=difference
    )


def aggregate_plan(
    entries: list[PlannedSnapshot], daily_target: MacroValues | None = None
) -> PlanTotals:
    meals: defaultdict[tuple[date, str], list[MealNutritionSnapshotValue]] = defaultdict(list)
    days: defaultdict[date, list[MealNutritionSnapshotValue]] = defaultdict(list)
    ordered = sorted(entries, key=lambda item: (item.local_date, item.meal_slot, item.position))
    for entry in ordered:
        meals[(entry.local_date, entry.meal_slot)].append(entry.nutrition)
        days[entry.local_date].append(entry.nutrition)
    meal_totals = {key: _total(values) for key, values in meals.items()}
    day_totals = {key: _total(values, daily_target) for key, values in days.items()}
    week_target = None
    if daily_target is not None:
        week_target = MacroValues(
            *(
                getattr(daily_target, field) * Decimal(7)
                if getattr(daily_target, field) is not None
                else None
                for field in FIELDS
            )
        )
    return PlanTotals(
        meal_totals, day_totals, _total([entry.nutrition for entry in ordered], week_target)
    )
