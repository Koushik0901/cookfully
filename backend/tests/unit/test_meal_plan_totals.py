from datetime import date
from decimal import Decimal

import pytest

from cookfully.domain.common import DomainError
from cookfully.domain.meal_snapshots import SnapshotSource, create_snapshot, refresh_snapshot
from cookfully.domain.nutrition import MacroValues
from cookfully.domain.plan_totals import PlannedSnapshot, aggregate_plan


def source(**overrides: object) -> SnapshotSource:
    values: dict[str, object] = {
        "recipe_id": None,
        "estimate_id": None,
        "recipe_title": "Training bowl",
        "macros": MacroValues(
            Decimal("501.500000"), Decimal("40.050000"), Decimal("60.050000"), Decimal("11.150000")
        ),
        "status": "estimated",
        "coverage_ratio": Decimal("0.950000"),
    }
    values.update(overrides)
    return SnapshotSource(**values)  # type: ignore[arg-type]


def test_servings_are_positive_three_decimal_and_snapshot_rounds_half_up() -> None:
    snapshot = create_snapshot(source(), Decimal("1.500"))
    assert snapshot.basis_servings == Decimal("1.500")
    assert snapshot.calories_kcal == Decimal("752")
    assert snapshot.protein_g == Decimal("60.1")
    assert snapshot.carbohydrate_g == Decimal("90.1")
    assert snapshot.fat_g == Decimal("16.7")
    with pytest.raises(DomainError, match="three decimal"):
        create_snapshot(source(), Decimal("1.0001"))
    with pytest.raises(DomainError, match="greater than zero"):
        create_snapshot(source(), Decimal("0"))


def test_partial_snapshot_retains_nulls_and_least_reliable_state() -> None:
    partial = create_snapshot(
        source(
            macros=MacroValues(Decimal("100"), None, Decimal("15"), Decimal("2")),
            status="partial",
            coverage_ratio=Decimal("0.700000"),
        ),
        Decimal("2.000"),
    )
    assert partial.protein_g is None
    report = aggregate_plan(
        [
            PlannedSnapshot(
                date(2026, 8, 10),
                "lunch",
                0,
                create_snapshot(
                    source(status="source_provided", coverage_ratio=Decimal("1")), Decimal("1")
                ),
            ),
            PlannedSnapshot(date(2026, 8, 10), "lunch", 1, partial),
        ]
    )
    assert report.week_total.status == "partial"
    assert report.week_total.coverage_ratio == Decimal("0.700000")
    assert report.week_total.protein_g is None


def test_meal_day_week_totals_sum_display_quantized_values_and_use_canonical_strings() -> None:
    first = create_snapshot(source(), Decimal("1.500"))
    second = create_snapshot(
        source(
            macros=MacroValues(
                Decimal("100.5"), Decimal("10.05"), Decimal("20.05"), Decimal("5.05")
            )
        ),
        Decimal("1"),
    )
    report = aggregate_plan(
        [
            PlannedSnapshot(date(2026, 8, 10), "breakfast", 0, first),
            PlannedSnapshot(date(2026, 8, 10), "breakfast", 1, second),
            PlannedSnapshot(date(2026, 8, 11), "dinner", 0, first),
        ],
        daily_target=MacroValues(Decimal("2000"), Decimal("150"), Decimal("200"), Decimal("60")),
    )
    breakfast = report.meal_totals[(date(2026, 8, 10), "breakfast")]
    assert breakfast.as_strings() == {
        "caloriesKcal": "853",
        "proteinG": "70.2",
        "carbohydrateG": "110.2",
        "fatG": "21.8",
    }
    assert report.week_total.as_strings() == {
        "caloriesKcal": "1605",
        "proteinG": "130.3",
        "carbohydrateG": "200.3",
        "fatG": "38.5",
    }
    assert report.day_totals[date(2026, 8, 10)].target_difference_strings() == {
        "caloriesKcal": "-1147",
        "proteinG": "-79.8",
        "carbohydrateG": "-89.8",
        "fatG": "-38.2",
    }


def test_refresh_is_explicit_and_replaces_instead_of_mutating_snapshot() -> None:
    original = create_snapshot(source(), Decimal("1.000"))
    replacement = refresh_snapshot(
        original,
        source(macros=MacroValues(Decimal("600"), Decimal("50"), Decimal("70"), Decimal("20"))),
        Decimal("2.000"),
    )
    assert original.calories_kcal == Decimal("502")
    assert original.basis_servings == Decimal("1.000")
    assert replacement.calories_kcal == Decimal("1200")
    assert replacement.basis_servings == Decimal("2.000")
    assert replacement is not original
