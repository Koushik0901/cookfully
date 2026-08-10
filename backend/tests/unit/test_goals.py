from datetime import date
from decimal import Decimal

import pytest

from vigor_vine.domain.common import DomainError
from vigor_vine.domain.goals import (
    DailyGoal,
    MealTarget,
    effective_periods_overlap,
    local_midnight,
    macro_calorie_difference,
    plan_week_dates,
    reportable_macro_calorie_difference,
    week_start_for,
)


def goal(**overrides: object) -> DailyGoal:
    values: dict[str, object] = {
        "mode": "cut",
        "maintenance_kcal": Decimal("2500.000000"),
        "target_kcal": Decimal("2200.000000"),
        "protein_g": Decimal("180.000000"),
        "carbohydrate_g": Decimal("220.000000"),
        "fat_g": Decimal("65.000000"),
        "effective_from": date(2026, 3, 1),
        "effective_to": None,
        "meal_targets": (),
    }
    values.update(overrides)
    return DailyGoal(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["target_kcal", "protein_g", "carbohydrate_g", "fat_g"])
def test_daily_goal_requires_every_core_target(field: str) -> None:
    with pytest.raises(DomainError, match="required"):
        goal(**{field: None})


def test_goal_validates_mode_energy_macros_dates_and_optional_meal_targets() -> None:
    with pytest.raises(DomainError, match="mode"):
        goal(mode="recomp")
    with pytest.raises(DomainError, match="greater than zero"):
        goal(maintenance_kcal=Decimal("0"))
    with pytest.raises(DomainError, match="non-negative"):
        goal(protein_g=Decimal("-0.1"))
    with pytest.raises(DomainError, match=r"(?i)at least one"):
        goal(protein_g=Decimal("0"), carbohydrate_g=Decimal("0"), fat_g=Decimal("0"))
    with pytest.raises(DomainError, match="effective end"):
        goal(effective_to=date(2026, 2, 28))

    value = goal(
        meal_targets=(
            MealTarget("breakfast", Decimal("500"), None, Decimal("55"), None),
            MealTarget("dinner", None, Decimal("70"), None, Decimal("25")),
        )
    )
    assert value.meal_targets[0].protein_g is None
    assert value.meal_targets[1].calories_kcal is None
    with pytest.raises(DomainError, match="unique"):
        goal(
            meal_targets=(
                MealTarget("lunch", None, None, None, None),
                MealTarget("lunch", None, None, None, None),
            )
        )


def test_effective_period_overlap_uses_inclusive_local_dates() -> None:
    assert effective_periods_overlap(date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 31), None)
    assert not effective_periods_overlap(
        date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 1), None
    )
    assert effective_periods_overlap(date(2026, 1, 1), None, date(2030, 1, 1), date(2030, 1, 2))


def test_macro_calorie_difference_is_exact_and_signed() -> None:
    assert macro_calorie_difference(
        target_kcal=Decimal("2200.000000"),
        protein_g=Decimal("180.000000"),
        carbohydrate_g=Decimal("220.000000"),
        fat_g=Decimal("65.000000"),
    ) == Decimal("-15.000000")
    assert (
        reportable_macro_calorie_difference(
            target_kcal=Decimal("2185.500000"),
            protein_g=Decimal("180.000000"),
            carbohydrate_g=Decimal("220.000000"),
            fat_g=Decimal("65.000000"),
        )
        is None
    )


def test_owner_week_start_and_timezone_preserve_seven_local_dates_across_dst() -> None:
    assert week_start_for(date(2026, 3, 11), 1) == date(2026, 3, 9)
    assert week_start_for(date(2026, 3, 11), 7) == date(2026, 3, 8)
    dates = plan_week_dates(date(2026, 3, 2))
    assert dates == tuple(date(2026, 3, day) for day in range(2, 9))
    before = local_midnight(date(2026, 3, 7), "America/Vancouver")
    after = local_midnight(date(2026, 3, 9), "America/Vancouver")
    assert before.utcoffset() != after.utcoffset()
    assert before.date() == date(2026, 3, 7)
    assert after.date() == date(2026, 3, 9)
    with pytest.raises(DomainError, match="timezone"):
        local_midnight(date(2026, 3, 7), "Mars/Olympus_Mons")
