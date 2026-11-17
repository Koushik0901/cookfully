"""Properties the domain rules must hold for *every* input, not only the examples we thought of.

Hypothesis generates the inputs (and shrinks a failure to the smallest one), so each test states a
rule in words: "an unknown value never becomes a smaller total", "a deduction can be reversed".
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cookfully.domain.common import (
    NUTRIENT_SCALE,
    DomainError,
    canonical_decimal,
    display_calories,
    display_macro,
    quantize_decimal,
)
from cookfully.domain.goals import (
    effective_periods_overlap,
    local_midnight,
    macro_calorie_difference,
    plan_week_dates,
    reportable_macro_calorie_difference,
    week_start_for,
)
from cookfully.domain.ingredient_nutrition.quantities import (
    PantryQuantity,
    apply_quantity_deduction,
    reverse_quantity_deduction,
)
from cookfully.domain.meal_snapshots import (
    MealNutritionSnapshotValue,
    SnapshotSource,
    create_snapshot,
)
from cookfully.domain.nutrition import IngredientNutrition, MacroValues, rollup_per_serving
from cookfully.domain.plan_totals import FIELDS, RELIABILITY, PlannedSnapshot, aggregate_plan

ONE_MICRO = Decimal("0.000001")


def decimals(
    low: str = "-1000000", high: str = "1000000", places: int = 6
) -> st.SearchStrategy[Decimal]:
    return st.decimals(
        min_value=Decimal(low),
        max_value=Decimal(high),
        places=places,
        allow_nan=False,
        allow_infinity=False,
    )


amounts = decimals("0", "100000", 3)
dates = st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31))


# --- Decimal formatting -----------------------------------------------------------------------


@given(decimals(), st.sampled_from([Decimal("1"), Decimal("0.1"), NUTRIENT_SCALE]))
def test_quantizing_twice_changes_nothing(value: Decimal, scale: Decimal) -> None:
    once = quantize_decimal(value, scale)
    assert quantize_decimal(once, scale) == once


@given(decimals())
def test_canonical_decimals_round_trip_and_have_one_spelling(value: Decimal) -> None:
    text = canonical_decimal(value)

    assert Decimal(text) == quantize_decimal(value, ONE_MICRO), "no precision is lost or invented"
    assert "e" not in text.lower(), "never scientific notation"
    assert text != "-0", "zero has a single spelling"
    assert "." not in text or not text.endswith(("0", ".")), "no trailing zeros"
    assert canonical_decimal(text) == text, "re-formatting a canonical value is a no-op"


@given(decimals())
def test_displayed_values_are_within_half_a_unit_of_the_truth(value: Decimal) -> None:
    assert abs(Decimal(display_calories(value)) - value) <= Decimal("0.5")
    assert abs(Decimal(display_macro(value)) - value) <= Decimal("0.05")


# --- Goals and calendar weeks -----------------------------------------------------------------


@given(
    decimals("0", "5000", 3),
    decimals("0", "500", 3),
    decimals("0", "500", 3),
    decimals("0", "500", 3),
)
def test_the_macro_calorie_gap_is_four_four_nine(
    target: Decimal, protein: Decimal, carbs: Decimal, fat: Decimal
) -> None:
    gap = macro_calorie_difference(
        target_kcal=target, protein_g=protein, carbohydrate_g=carbs, fat_g=fat
    )
    assert gap == protein * 4 + carbs * 4 + fat * 9 - target

    on_target = macro_calorie_difference(
        target_kcal=protein * 4 + carbs * 4 + fat * 9,
        protein_g=protein,
        carbohydrate_g=carbs,
        fat_g=fat,
    )
    assert on_target == 0


@given(
    decimals("0", "5000", 3),
    decimals("0", "500", 3),
    decimals("0", "500", 3),
    decimals("0", "500", 3),
    decimals("0", "100", 3),
)
def test_a_gap_is_reported_only_when_it_exceeds_the_tolerance(
    target: Decimal, protein: Decimal, carbs: Decimal, fat: Decimal, tolerance: Decimal
) -> None:
    gap = macro_calorie_difference(
        target_kcal=target, protein_g=protein, carbohydrate_g=carbs, fat_g=fat
    )
    reported = reportable_macro_calorie_difference(
        target_kcal=target,
        protein_g=protein,
        carbohydrate_g=carbs,
        fat_g=fat,
        tolerance=tolerance,
    )
    assert reported == (gap if abs(gap) > tolerance else None)


@given(dates, st.integers(min_value=1, max_value=7))
def test_a_plan_week_starts_on_the_chosen_weekday_and_contains_the_date(
    day: date, week_starts_on: int
) -> None:
    start = week_start_for(day, week_starts_on)

    assert start.isoweekday() == week_starts_on
    assert start <= day < start + timedelta(days=7)
    assert week_start_for(start, week_starts_on) == start, "a week start is its own week start"
    week = plan_week_dates(start)
    assert day in week
    assert week == tuple(start + timedelta(days=offset) for offset in range(7))


@given(dates, st.integers().filter(lambda value: not 1 <= value <= 7))
def test_a_week_start_outside_one_to_seven_is_a_client_error(day: date, bad: int) -> None:
    with pytest.raises(DomainError) as error:
        week_start_for(day, bad)
    assert error.value.status == 422


period = st.tuples(st.integers(0, 40), st.one_of(st.none(), st.integers(0, 40))).filter(
    lambda bounds: bounds[1] is None or bounds[1] >= bounds[0]
)


@given(period, period)
def test_overlapping_goal_periods_match_a_day_by_day_check(first: Any, second: Any) -> None:
    base = date(2026, 1, 1)

    def span(bounds: tuple[int, int | None]) -> tuple[date, date | None]:
        start, end = bounds
        return base + timedelta(days=start), None if end is None else base + timedelta(days=end)

    (first_start, first_end), (second_start, second_end) = span(first), span(second)
    overlap = effective_periods_overlap(first_start, first_end, second_start, second_end)

    def covers(start: date, end: date | None, day: date) -> bool:
        return start <= day and (end is None or day <= end)

    brute_force = any(
        covers(first_start, first_end, base + timedelta(days=offset))
        and covers(second_start, second_end, base + timedelta(days=offset))
        for offset in range(-1, 90)
    )
    assert overlap is brute_force
    assert overlap == effective_periods_overlap(second_start, second_end, first_start, first_end)


# --- Plan totals: unknown never becomes smaller -----------------------------------------------

STATUSES = list(RELIABILITY)
quantity = st.one_of(st.none(), decimals("0", "2000", 1))
slots = st.sampled_from(["breakfast", "lunch", "dinner"])


@st.composite
def snapshots(draw: st.DrawFn) -> MealNutritionSnapshotValue:
    return MealNutritionSnapshotValue(
        recipe_id=None,
        estimate_id=None,
        recipe_title="Meal",
        basis_servings=Decimal("1"),
        calories_kcal=draw(quantity),
        protein_g=draw(quantity),
        carbohydrate_g=draw(quantity),
        fat_g=draw(quantity),
        status=draw(st.sampled_from(STATUSES)),
        coverage_ratio=draw(decimals("0", "1", 3)),
    )


@st.composite
def plans(draw: st.DrawFn) -> list[PlannedSnapshot]:
    count = draw(st.integers(min_value=1, max_value=8))
    positions = itertools.count()
    return [
        PlannedSnapshot(
            draw(st.sampled_from([date(2026, 8, 10) + timedelta(days=n) for n in range(3)])),
            draw(slots),
            next(positions),
            draw(snapshots()),
        )
        for _ in range(count)
    ]


def expected_sum(values: list[Decimal | None]) -> Decimal | None:
    return None if any(value is None for value in values) else sum(values, Decimal(0))  # type: ignore[arg-type]


@given(plans(), st.randoms(use_true_random=False))
def test_plan_totals_do_not_depend_on_the_order_entries_arrive_in(
    entries: list[PlannedSnapshot], random: Any
) -> None:
    shuffled = list(entries)
    random.shuffle(shuffled)

    assert aggregate_plan(shuffled) == aggregate_plan(entries)


@given(plans())
def test_a_total_is_the_exact_sum_and_an_unknown_part_makes_it_unknown(
    entries: list[PlannedSnapshot],
) -> None:
    totals = aggregate_plan(entries)

    for field in FIELDS:
        every = [getattr(entry.nutrition, field) for entry in entries]
        assert getattr(totals.week_total, field) == expected_sum(every), (
            "one missing value must not turn into a smaller, confident-looking total"
        )
        for day, day_total in totals.day_totals.items():
            same_day = [
                getattr(entry.nutrition, field) for entry in entries if entry.local_date == day
            ]
            assert getattr(day_total, field) == expected_sum(same_day)
        for (day, slot), meal_total in totals.meal_totals.items():
            same_meal = [
                getattr(entry.nutrition, field)
                for entry in entries
                if (entry.local_date, entry.meal_slot) == (day, slot)
            ]
            assert getattr(meal_total, field) == expected_sum(same_meal)


@given(plans())
def test_a_total_is_only_as_reliable_and_as_complete_as_its_weakest_part(
    entries: list[PlannedSnapshot],
) -> None:
    week = aggregate_plan(entries).week_total

    assert week.status == min((e.nutrition.status for e in entries), key=RELIABILITY.__getitem__)
    assert week.coverage_ratio == min(e.nutrition.coverage_ratio for e in entries)


@given(plans(), decimals("0", "5000", 1))
def test_targets_are_compared_per_day_and_scaled_by_seven_for_the_week(
    entries: list[PlannedSnapshot], daily_calories: Decimal
) -> None:
    target = MacroValues(daily_calories, None, None, None)
    totals = aggregate_plan(entries, target)

    for day_total in totals.day_totals.values():
        assert day_total.target_difference is not None
        calories = day_total.calories_kcal
        gap = day_total.target_difference.calories_kcal
        assert gap == (None if calories is None else calories - daily_calories)
        assert day_total.target_difference.protein_g is None, "no target, so no gap"
    week_gap = totals.week_total.target_difference
    assert week_gap is not None
    week_calories = totals.week_total.calories_kcal
    assert week_gap.calories_kcal == (
        None if week_calories is None else week_calories - daily_calories * 7
    )


# --- Recipe rollups ---------------------------------------------------------------------------

grams = decimals("0", "5000", 3)


@st.composite
def contributions(draw: st.DrawFn) -> list[IngredientNutrition]:
    return [
        IngredientNutrition(
            macros=MacroValues(draw(grams), draw(grams), draw(grams), draw(grams)),
            matched=draw(st.booleans()),
            provisional=draw(st.booleans()),
        )
        for _ in range(draw(st.integers(min_value=0, max_value=6)))
    ]


servings = decimals("0.5", "20", 3)


@given(contributions(), servings)
def test_a_recipe_rollup_is_the_per_serving_share_of_its_matched_ingredients(
    items: list[IngredientNutrition], count: Decimal
) -> None:
    result = rollup_per_serving(items, count, coverage=Decimal("1"))
    counted = [item for item in items if item.matched or item.provisional]

    for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g"):
        value = getattr(result.macros, field)
        if not counted:
            assert value is None, "nothing matched means nothing is claimed"
            continue
        total = sum((getattr(item.macros, field) for item in counted), Decimal(0))
        assert abs(value * result.basis_servings - total) <= ONE_MICRO * result.basis_servings


@given(contributions(), servings)
def test_doubling_the_servings_halves_each_serving(
    items: list[IngredientNutrition], count: Decimal
) -> None:
    single = rollup_per_serving(items, count, coverage=Decimal("1"))
    double = rollup_per_serving(items, count * 2, coverage=Decimal("1"))

    for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g"):
        one, two = getattr(single.macros, field), getattr(double.macros, field)
        if one is None:
            assert two is None
        else:
            assert abs(one - two * 2) <= 2 * ONE_MICRO


@given(contributions(), st.one_of(decimals("-5", "0", 3), decimals("-5", "-0.001", 3)))
def test_a_recipe_cannot_have_zero_or_negative_servings(
    items: list[IngredientNutrition], bad: Decimal
) -> None:
    with pytest.raises(DomainError) as error:
        rollup_per_serving(items, bad, coverage=Decimal("1"))
    assert error.value.code == "invalid_servings"


@given(
    st.decimals(min_value=Decimal("-5"), max_value=Decimal("5"), places=3).filter(
        lambda value: not Decimal(0) <= value <= Decimal(1)
    )
)
def test_coverage_outside_zero_to_one_is_rejected(coverage: Decimal) -> None:
    with pytest.raises(DomainError) as error:
        rollup_per_serving([], Decimal("2"), coverage=coverage)
    assert error.value.code == "invalid_coverage"


# --- Meal snapshots ---------------------------------------------------------------------------


@given(decimals("0", "3000", 1), servings)
def test_more_servings_never_lower_a_snapshots_calories(calories: Decimal, count: Decimal) -> None:
    source = SnapshotSource(
        recipe_id=UUID(int=1),
        estimate_id=None,
        recipe_title="Soup",
        macros=MacroValues(calories, None, None, None),
        status="estimated",
        coverage_ratio=Decimal("0.8"),
    )

    smaller = create_snapshot(source, count)
    larger = create_snapshot(source, count + Decimal("1"))

    assert smaller.calories_kcal is not None and larger.calories_kcal is not None
    assert larger.calories_kcal >= smaller.calories_kcal
    assert smaller.protein_g is None, "an unknown macro stays unknown when scaled"
    assert smaller.coverage_ratio == Decimal("0.8"), "scaling servings never changes coverage"


# --- Pantry deductions ------------------------------------------------------------------------

MASS = ["g", "kg", "oz", "lb"]
VOLUME = ["ml", "l", "tsp", "tbsp", "cup"]


@st.composite
def pantry_and_grocery(draw: st.DrawFn) -> tuple[PantryQuantity, PantryQuantity]:
    units = draw(st.sampled_from([MASS, VOLUME, ["item"]]))
    return (
        PantryQuantity(draw(decimals("0", "5000", 3)), draw(st.sampled_from(units)), 1),
        PantryQuantity(draw(decimals("0", "5000", 3)), draw(st.sampled_from(units)), 1),
    )


@given(pantry_and_grocery())
def test_a_deduction_never_goes_negative_and_exhausts_whichever_side_is_used_up(
    pair: tuple[PantryQuantity, PantryQuantity],
) -> None:
    pantry, grocery = pair
    deduction = apply_quantity_deduction(pantry, grocery)

    assert deduction.pantry_after.quantity >= 0, "the database forbids a negative pantry quantity"
    assert deduction.grocery_after.quantity >= 0
    assert deduction.grocery_amount <= grocery.quantity
    assert deduction.pantry_amount <= quantize_decimal(pantry.quantity, NUTRIENT_SCALE)
    assert deduction.pantry_after.quantity == 0 or deduction.grocery_after.quantity == 0, (
        "a deduction ends when one side runs out; no 'dust' is left on both"
    )
    assert deduction.pantry_after.version == pantry.version + 1
    assert deduction.grocery_after.version == grocery.version + 1


@pytest.mark.parametrize(
    ("pantry", "pantry_unit", "grocery", "grocery_unit"),
    [("100", "ml", "5", "cup"), ("250", "ml", "2", "cup"), ("500", "g", "3", "lb")],
)
def test_ordinary_mixed_unit_deductions_do_not_leave_negative_or_dust_quantities(
    pantry: str, pantry_unit: str, grocery: str, grocery_unit: str
) -> None:
    """Found by the property above: 100 ml against 5 cups used to leave -0.00008 ml."""

    deduction = apply_quantity_deduction(
        PantryQuantity(Decimal(pantry), pantry_unit, 1),
        PantryQuantity(Decimal(grocery), grocery_unit, 1),
    )

    assert deduction.pantry_after.quantity == 0, "the whole pantry stock was used"
    assert deduction.grocery_after.quantity > 0, "the rest of the list item remains"


@given(pantry_and_grocery())
def test_a_deduction_can_be_reversed_to_the_exact_starting_quantities(
    pair: tuple[PantryQuantity, PantryQuantity],
) -> None:
    pantry, grocery = pair
    deduction = apply_quantity_deduction(pantry, grocery)

    restored_pantry, restored_grocery = reverse_quantity_deduction(
        deduction, pantry=deduction.pantry_after, grocery=deduction.grocery_after
    )

    assert restored_pantry.quantity == deduction.pantry_before.quantity
    assert restored_grocery.quantity == deduction.grocery_before.quantity
    assert restored_pantry.quantity == quantize_decimal(pantry.quantity, NUTRIENT_SCALE)
    assert restored_grocery.quantity == quantize_decimal(grocery.quantity, NUTRIENT_SCALE)


# --- Time zones -------------------------------------------------------------------------------


@given(dates, st.sampled_from(["UTC", "America/Vancouver", "Asia/Kolkata", "Pacific/Chatham"]))
def test_local_midnight_is_the_first_instant_of_the_local_date(day: date, zone: str) -> None:
    moment = local_midnight(day, zone)

    assert moment.date() == day
    assert (moment.hour, moment.minute, moment.second) == (0, 0, 0)


@given(dates, st.sampled_from(["", "../etc/passwd", "Not/AZone", "/UTC", "utc\x00"]))
def test_local_midnight_rejects_a_malformed_zone_as_a_client_error(day: date, zone: str) -> None:
    """``ZoneInfo("")`` raises ValueError, which used to escape as a 500."""

    with pytest.raises(DomainError) as error:
        local_midnight(day, zone)
    assert (error.value.code, error.value.status) == ("invalid_timezone", 422)
