from __future__ import annotations

from datetime import date
from decimal import Decimal
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.domain.meal_snapshots import SnapshotSource, create_snapshot
from vigor_vine.domain.nutrition import MacroValues
from vigor_vine.domain.plan_totals import PlannedSnapshot, aggregate_plan
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.infrastructure.models.plans import (
    MealNutritionSnapshot,
    MealPlan,
    MealPlanEntry,
    UserGoal,
)
from vigor_vine.infrastructure.models.recipes import Recipe


def test_recipe_edit_and_delete_leave_detached_snapshot_history(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory.begin() as session:
        owner = OwnerAccount(
            email="history@example.com",
            display_name="History",
            password_hash="not-used",
            timezone="America/Vancouver",
            week_starts_on=1,
        )
        session.add(owner)
        session.flush()
        goal = UserGoal(
            owner_id=owner.id,
            mode="maintain",
            maintenance_kcal=Decimal("2200"),
            target_kcal=Decimal("2200"),
            protein_g=Decimal("150"),
            carbohydrate_g=Decimal("250"),
            fat_g=Decimal("65"),
            effective_from=date(2026, 1, 1),
        )
        session.add(goal)
        session.flush()
        plan = MealPlan(
            owner_id=owner.id,
            week_start=date(2026, 3, 9),
            timezone=owner.timezone,
            goal_id=goal.id,
        )
        session.add(plan)
        session.flush()
        recipe = Recipe(
            title="Historical bowl",
            yield_quantity=Decimal("2.000"),
            yield_unit="servings",
            status="ready",
            nutrition_state="estimated",
            input_hash="sha256:history",
        )
        session.add(recipe)
        session.flush()
        snapshot = MealNutritionSnapshot(
            recipe_id=recipe.id,
            estimate_id=None,
            basis_servings=Decimal("1.500"),
            calories_kcal=Decimal("752"),
            protein_g=Decimal("60.1"),
            carbohydrate_g=Decimal("90.1"),
            fat_g=Decimal("16.7"),
            nutrition_state="estimated",
            coverage_ratio=Decimal("0.950000"),
        )
        session.add(snapshot)
        session.flush()
        entry = MealPlanEntry(
            meal_plan_id=plan.id,
            local_date=date(2026, 3, 9),
            meal_slot="breakfast",
            position=0,
            recipe_id=recipe.id,
            recipe_title_snapshot="Historical bowl",
            servings=Decimal("1.500"),
            nutrition_snapshot_id=snapshot.id,
            origin="manual",
        )
        session.add(entry)
        session.flush()
        entry_id = entry.id
        snapshot_id = snapshot.id
        recipe.title = "Renamed bowl"

    with session_factory.begin() as session:
        entry = session.get(MealPlanEntry, entry_id)
        assert entry is not None and entry.recipe_title_snapshot == "Historical bowl"
        assert entry.nutrition_snapshot_id == snapshot_id
        recipe = session.scalar(select(Recipe).where(Recipe.title == "Renamed bowl"))
        assert recipe is not None
        session.delete(recipe)

    with session_factory() as session:
        entry = session.get(MealPlanEntry, entry_id)
        snapshot = session.get(MealNutritionSnapshot, snapshot_id)
        assert entry is not None and entry.recipe_id is None
        assert snapshot is not None and snapshot.recipe_id is None
        assert entry.recipe_title_snapshot == "Historical bowl"
        assert snapshot.calories_kcal == Decimal("752")


def test_display_quantized_snapshots_and_fifty_entry_aggregation_are_fast() -> None:
    source = SnapshotSource(
        recipe_id=None,
        estimate_id=None,
        recipe_title="Fixture",
        macros=MacroValues(Decimal("501.5"), Decimal("40.05"), Decimal("60.05"), Decimal("11.15")),
        status="estimated",
        coverage_ratio=Decimal("0.95"),
    )
    started = perf_counter()
    entries = [
        PlannedSnapshot(
            date(2026, 3, 9 + (index % 7)),
            f"slot-{index % 4}",
            index,
            create_snapshot(source, Decimal("1.500")),
        )
        for index in range(50)
    ]
    report = aggregate_plan(entries)
    elapsed = perf_counter() - started
    assert report.week_total.calories_kcal == Decimal("37600")
    assert report.week_total.protein_g == Decimal("3005.0")
    assert elapsed < 2
