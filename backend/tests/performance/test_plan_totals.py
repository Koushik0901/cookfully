from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from math import ceil
from time import perf_counter

from cookfully.domain.meal_snapshots import SnapshotSource, create_snapshot
from cookfully.domain.nutrition import MacroValues
from cookfully.domain.plan_totals import PlannedSnapshot, aggregate_plan

REFERENCE_ENTRY = SnapshotSource(
    recipe_id=None,
    estimate_id=None,
    recipe_title="50-entry reference bowl",
    macros=MacroValues(
        Decimal("501.500000"),
        Decimal("40.050000"),
        Decimal("60.050000"),
        Decimal("11.150000"),
    ),
    status="estimated",
    coverage_ratio=Decimal("0.950000"),
)
REFERENCE_TARGET = MacroValues(
    Decimal("2200.000000"),
    Decimal("180.000000"),
    Decimal("220.000000"),
    Decimal("65.000000"),
)


def reference_plan() -> list[PlannedSnapshot]:
    monday = date(2026, 3, 9)
    return [
        PlannedSnapshot(
            local_date=monday + timedelta(days=index % 7),
            meal_slot=("breakfast", "lunch", "dinner", "snack")[index % 4],
            position=index,
            nutrition=create_snapshot(REFERENCE_ENTRY, Decimal("1.500")),
        )
        for index in range(50)
    ]


def percentile(samples: list[float], percentile_value: float) -> float:
    ordered = sorted(samples)
    return ordered[max(0, ceil(percentile_value * len(ordered)) - 1)]


def test_fifty_entry_exact_sum_and_p95_report(capsys: object) -> None:
    entries = reference_plan()
    for _ in range(10):
        aggregate_plan(entries, REFERENCE_TARGET)

    samples: list[float] = []
    report = None
    for _ in range(100):
        started = perf_counter()
        report = aggregate_plan(entries, REFERENCE_TARGET)
        samples.append(perf_counter() - started)

    assert report is not None
    assert report.week_total.as_strings() == {
        "caloriesKcal": "37600",
        "proteinG": "3005.0",
        "carbohydrateG": "4505.0",
        "fatG": "835.0",
    }
    assert report.week_total.target_difference_strings() == {
        "caloriesKcal": "22200",
        "proteinG": "1745.0",
        "carbohydrateG": "2965.0",
        "fatG": "380.0",
    }
    p50 = percentile(samples, 0.50)
    p95 = percentile(samples, 0.95)
    maximum = max(samples)
    print(
        "50-entry aggregate latency "
        f"p50={p50 * 1000:.3f}ms p95={p95 * 1000:.3f}ms max={maximum * 1000:.3f}ms"
    )
    assert p95 < 2.0
