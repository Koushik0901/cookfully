from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cookfully.domain.common import NUTRIENT_SCALE, DomainError, quantize_decimal

GoalMode = Literal["cut", "maintain", "bulk"]
MACRO_CALORIE_DISPLAY_TOLERANCE = Decimal("1.000000")


def _required_decimal(name: str, value: Decimal | None, *, positive: bool = False) -> Decimal:
    if value is None:
        raise DomainError("goal_target_required", f"{name} is required.", 422)
    result = quantize_decimal(value, NUTRIENT_SCALE)
    if result < 0:
        raise DomainError("goal_target_negative", f"{name} must be non-negative.", 422)
    if positive and result == 0:
        raise DomainError("goal_target_zero", f"{name} must be greater than zero.", 422)
    return result


@dataclass(frozen=True, slots=True)
class MealTarget:
    meal_slot: str
    calories_kcal: Decimal | None
    protein_g: Decimal | None
    carbohydrate_g: Decimal | None
    fat_g: Decimal | None

    def __post_init__(self) -> None:
        if not self.meal_slot.strip():
            raise DomainError("meal_slot_required", "Meal slot is required.", 422)
        for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _required_decimal(field, value))


@dataclass(frozen=True, slots=True)
class DailyGoal:
    mode: GoalMode
    maintenance_kcal: Decimal
    target_kcal: Decimal
    protein_g: Decimal
    carbohydrate_g: Decimal
    fat_g: Decimal
    effective_from: date
    effective_to: date | None = None
    meal_targets: tuple[MealTarget, ...] = ()
    dietary_fiber_g: Decimal | None = None
    sodium_mg: Decimal | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"cut", "maintain", "bulk"}:
            raise DomainError("goal_mode_invalid", "Select a valid goal mode.", 422)
        object.__setattr__(
            self,
            "maintenance_kcal",
            _required_decimal("Maintenance calories", self.maintenance_kcal, positive=True),
        )
        object.__setattr__(
            self,
            "target_kcal",
            _required_decimal("Daily calories", self.target_kcal, positive=True),
        )
        for field, label in (
            ("protein_g", "Daily protein"),
            ("carbohydrate_g", "Daily carbohydrate"),
            ("fat_g", "Daily fat"),
        ):
            object.__setattr__(self, field, _required_decimal(label, getattr(self, field)))
        if not any(getattr(self, field) > 0 for field in ("protein_g", "carbohydrate_g", "fat_g")):
            raise DomainError(
                "goal_macros_empty", "At least one daily macro must be greater than zero.", 422
            )
        for field, label in (("dietary_fiber_g", "Daily fiber"), ("sodium_mg", "Daily sodium")):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, _required_decimal(label, value))
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise DomainError(
                "goal_period_invalid",
                "The effective end date cannot be before the start date.",
                422,
            )
        slots = [target.meal_slot.casefold() for target in self.meal_targets]
        if len(slots) != len(set(slots)):
            raise DomainError("meal_target_duplicate", "Meal target slots must be unique.", 422)


def macro_calorie_difference(
    *,
    target_kcal: Decimal,
    protein_g: Decimal,
    carbohydrate_g: Decimal,
    fat_g: Decimal,
) -> Decimal:
    derived = protein_g * Decimal(4) + carbohydrate_g * Decimal(4) + fat_g * Decimal(9)
    return quantize_decimal(derived - target_kcal, NUTRIENT_SCALE)


def reportable_macro_calorie_difference(
    *,
    target_kcal: Decimal,
    protein_g: Decimal,
    carbohydrate_g: Decimal,
    fat_g: Decimal,
    tolerance: Decimal = MACRO_CALORIE_DISPLAY_TOLERANCE,
) -> Decimal | None:
    normalized_tolerance = quantize_decimal(tolerance, NUTRIENT_SCALE)
    if normalized_tolerance < 0:
        raise DomainError("goal_tolerance_negative", "Goal tolerance must be non-negative.", 422)
    difference = macro_calorie_difference(
        target_kcal=target_kcal,
        protein_g=protein_g,
        carbohydrate_g=carbohydrate_g,
        fat_g=fat_g,
    )
    return difference if abs(difference) > normalized_tolerance else None


def effective_periods_overlap(
    first_start: date,
    first_end: date | None,
    second_start: date,
    second_end: date | None,
) -> bool:
    return first_start <= (second_end or date.max) and second_start <= (first_end or date.max)


def week_start_for(value: date, week_starts_on: int) -> date:
    if not 1 <= week_starts_on <= 7:
        raise DomainError(
            "invalid_week_start", "Week start must be an ISO weekday from 1 to 7.", 422
        )
    return value - timedelta(days=(value.isoweekday() - week_starts_on) % 7)


def plan_week_dates(week_start: date) -> tuple[date, ...]:
    return tuple(week_start + timedelta(days=offset) for offset in range(7))


def local_midnight(value: date, timezone: str) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise DomainError("invalid_timezone", "Select a valid IANA timezone.", 422) from exc
    return datetime.combine(value, time.min, tzinfo=zone)
