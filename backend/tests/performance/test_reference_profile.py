from __future__ import annotations

import json
import os
import platform
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from cookfully.api.main import create_app
from cookfully.application.meal_plans import GoalWrite, MealPlanEntryWrite
from cookfully.domain.common import utc_now
from cookfully.domain.suggestion_solver import (
    SuggestionCandidate,
    SuggestionProblem,
    SuggestionTarget,
    solve_suggestion,
)
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.nutrition import NutritionEstimate
from cookfully.infrastructure.models.recipes import Ingredient, Recipe

RUNS = 3
WARMUPS = 10
OBSERVATIONS = 100
RECIPE_COUNT = 10_000
PLAN_ENTRY_COUNT = 50
# Keep the synthetic plan writable as the calendar advances. The application
# intentionally rejects mutations for past planning days, so a fixed historical
# date would make this reference benchmark fail before measuring latency.
_TODAY = date.today()
WEEK_START = _TODAY + timedelta(days=7 - _TODAY.weekday())
BUDGETS_MS = {
    "recipeLibraryRead": 500.0,
    "recipeSearch": 500.0,
    "planMutation50Entries": 500.0,
    "jobAcknowledgement": 1000.0,
    "jobPolling": 500.0,
    "groceryGeneration50Entries": 500.0,
    "suggestionSolve": 10_000.0,
}
pytestmark = [
    pytest.mark.performance,
    pytest.mark.skipif(
        os.environ.get("COOKFULLY_REFERENCE_PROFILE") != "1",
        reason="Run through deploy/compose.performance.yaml for reference-profile evidence.",
    ),
]


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[max(0, ceil(len(ordered) * fraction) - 1)]


def _measure(operation: Callable[[], None]) -> list[dict[str, float | int]]:
    runs: list[dict[str, float | int]] = []
    for run_number in range(1, RUNS + 1):
        for _ in range(WARMUPS):
            operation()
        samples: list[float] = []
        for _ in range(OBSERVATIONS):
            started = perf_counter()
            operation()
            samples.append((perf_counter() - started) * 1000)
        runs.append(
            {
                "run": run_number,
                "observations": len(samples),
                "p50Ms": round(median(samples), 3),
                "p95Ms": round(_percentile(samples, 0.95), 3),
                "maxMs": round(max(samples), 3),
            }
        )
    return runs


def _profile() -> dict[str, Any]:
    memory_kib = int(
        next(
            line.split()[1]
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
            if line.startswith("MemTotal:")
        )
    )
    affinity = sorted(os.sched_getaffinity(0))
    return {
        "os": platform.system(),
        "architecture": platform.machine(),
        "cpuAffinity": affinity,
        "cpuCount": len(affinity),
        "memoryKiB": memory_kib,
        "storageClass": os.environ.get("COOKFULLY_REFERENCE_STORAGE", "unverified"),
        "containerized": Path("/.dockerenv").exists(),
    }


def _assert_reference_profile(profile: dict[str, Any]) -> None:
    assert profile["os"] == "Linux"
    assert profile["architecture"] == "x86_64"
    assert profile["cpuCount"] == 4
    assert 7_500_000 <= profile["memoryKiB"] <= 8_500_000
    assert profile["storageClass"] == "ssd"
    assert profile["containerized"] is True


def _authenticate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "email": "performance@example.com",
            "password": os.environ["COOKFULLY_OWNER_BOOTSTRAP_PASSWORD"],
        },
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def _seed_recipes(factory: sessionmaker[Session], owner_id: UUID) -> UUID:
    recipe_ids = [uuid4() for _ in range(RECIPE_COUNT)]
    rows = [
        {
            "id": recipe_id,
            "title": (
                f"Needle reference recipe {index:05d}"
                if index % 997 == 0
                else f"Reference recipe {index:05d}"
            ),
            "yield_quantity": Decimal("2.000"),
            "yield_unit": "servings",
            "status": "ready",
            "nutrition_state": "pending",
            "input_hash": f"sha256:{index:064x}",
            "version": 1,
        }
        for index, recipe_id in enumerate(recipe_ids)
    ]
    with factory.begin() as session:
        for offset in range(0, len(rows), 1000):
            session.execute(insert(Recipe), rows[offset : offset + 1000])
        recipe_id = recipe_ids[0]
        ingredient = Ingredient(
            recipe_id=recipe_id,
            position=0,
            original_text="200 g red onion",
            quantity_min=Decimal("200.000000"),
            quantity_max=Decimal("200.000000"),
            unit_code="g",
            unit_text="g",
            food_name="red onion",
            optional=False,
            parse_status="parsed",
            version=1,
        )
        session.add(ingredient)
        estimate = NutritionEstimate(
            recipe_id=recipe_id,
            status="estimated",
            basis_servings=Decimal("2.000"),
            calories_kcal=Decimal("500.000000"),
            protein_g=Decimal("40.000000"),
            carbohydrate_g=Decimal("60.000000"),
            fat_g=Decimal("10.000000"),
            coverage_ratio=Decimal("1.000000"),
            source_label="performance fixture",
            input_hash="sha256:performance-estimate",
            pipeline_version="performance-v1",
            calculated_at=utc_now(),
        )
        session.add(estimate)
        session.flush()
        session.execute(
            update(Recipe)
            .where(Recipe.id == recipe_id)
            .values(active_estimate_id=estimate.id, nutrition_state="estimated")
        )
    assert owner_id
    return recipe_ids[0]


def _suggestion_problem() -> SuggestionProblem:
    candidates = tuple(
        SuggestionCandidate(
            recipe_id=UUID(int=index + 1),
            recipe_title=f"Candidate {index + 1}",
            calories_kcal=Decimal("250"),
            protein_g=Decimal("20"),
            carbohydrate_g=Decimal("25"),
            fat_g=Decimal("7.5"),
            serving_increment=Decimal("1"),
            minimum_servings=Decimal("1"),
            maximum_servings=Decimal("1"),
            available=True,
        )
        for index in range(20)
    )
    return SuggestionProblem(
        candidates=candidates,
        target=SuggestionTarget(Decimal("500"), Decimal("40"), Decimal("50"), Decimal("15")),
        tolerances=SuggestionTarget(*(Decimal("0") for _ in range(4))),
        max_entries=2,
        time_limit_seconds=9.5,
    )


def test_linux_reference_profile(isolated_database_url: str, tmp_path: Path) -> None:
    profile = _profile()
    _assert_reference_profile(profile)
    settings = Settings(
        environment="test",
        database_url=isolated_database_url,
        owner_email="performance@example.com",
        owner_bootstrap_password=os.environ["COOKFULLY_OWNER_BOOTSTRAP_PASSWORD"],
        media_root=tmp_path / "media",
        export_root=tmp_path / "exports",
        erasure_ledger_root=tmp_path / "ledger",
    )
    app = create_app(settings)
    engine = create_engine(isolated_database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    report: dict[str, Any] = {
        "profile": profile,
        "dataset": {
            "recipes": RECIPE_COUNT,
            "planEntries": PLAN_ENTRY_COUNT,
            "warmupsPerRun": WARMUPS,
            "observationsPerRun": OBSERVATIONS,
            "runs": RUNS,
        },
        "budgetsMs": BUDGETS_MS,
        "paths": {},
    }

    with TestClient(app) as client:
        headers = _authenticate(client)
        with factory() as session:
            owner_id = session.scalar(
                select(OwnerAccount.id).where(OwnerAccount.email == "performance@example.com")
            )
        assert owner_id is not None
        recipe_id = _seed_recipes(factory, owner_id)
        app.state.goals.put(
            owner_id,
            GoalWrite(
                mode="maintain",
                maintenance_kcal=Decimal("2200"),
                target_kcal=Decimal("2200"),
                protein_g=Decimal("180"),
                carbohydrate_g=Decimal("220"),
                fat_g=Decimal("65"),
                effective_from=WEEK_START,
                effective_to=None,
            ),
        )
        entries = [
            app.state.meal_plans.add(
                owner_id,
                WEEK_START,
                MealPlanEntryWrite(
                    local_date=WEEK_START,
                    meal_slot="performance",
                    recipe_id=recipe_id,
                    servings=Decimal("1.000"),
                    position=index,
                ),
            )
            for index in range(PLAN_ENTRY_COUNT)
        ]
        poll_job = app.state.jobs.accept(
            kind="performance_poll",
            aggregate_type="performance",
            aggregate_id=uuid4(),
            input_hash="sha256:performance-poll",
            trace_id="performance",
        )

        def recipe_read() -> None:
            response = client.get("/api/v1/recipes", params={"limit": 30})
            assert response.status_code == 200 and len(response.json()["items"]) == 30

        def recipe_search() -> None:
            response = client.get("/api/v1/recipes", params={"query": "Needle", "limit": 30})
            assert response.status_code == 200 and response.json()["items"]

        plan_counter = 0

        def plan_mutation() -> None:
            nonlocal plan_counter
            index = plan_counter % PLAN_ENTRY_COUNT
            entry = entries[index]
            response = client.patch(
                f"/api/v1/meal-plan-entries/{entry.id}",
                headers={
                    **headers,
                    "If-Match": f'"{entry.version}"',
                    "Idempotency-Key": f"performance-plan-{plan_counter:06d}",
                },
                json={
                    "localDate": WEEK_START.isoformat(),
                    "mealSlot": "performance",
                    "recipeId": str(recipe_id),
                    "servings": "1.001" if plan_counter % 2 else "1.000",
                    "position": index,
                    "refreshNutrition": False,
                },
            )
            assert response.status_code == 200
            entries[index] = app.state.meal_plans.get_entry(owner_id, entry.id).entry
            plan_counter += 1

        ack_counter = 0

        def job_acknowledgement() -> None:
            nonlocal ack_counter
            response = client.post(
                "/api/v1/recipes/import",
                headers={
                    **headers,
                    "Idempotency-Key": f"performance-import-{ack_counter:06d}",
                },
                json={"url": f"https://example.test/recipe/{ack_counter}"},
            )
            assert response.status_code == 202
            ack_counter += 1

        def job_polling() -> None:
            response = client.get(f"/api/v1/jobs/{poll_job.id}")
            assert response.status_code == 200 and response.json()["status"] == "queued"

        grocery_counter = 0

        def grocery_generation() -> None:
            nonlocal grocery_counter
            response = client.post(
                f"/api/v1/meal-plans/{WEEK_START.isoformat()}/grocery-list",
                headers={
                    **headers,
                    "Idempotency-Key": f"performance-grocery-{grocery_counter:06d}",
                },
            )
            assert response.status_code == 200 and len(response.json()["items"]) == 1
            grocery_counter += 1

        suggestion = _suggestion_problem()

        def suggestion_solve() -> None:
            result = solve_suggestion(suggestion)
            assert result.status == "feasible"

        operations = {
            "recipeLibraryRead": recipe_read,
            "recipeSearch": recipe_search,
            "planMutation50Entries": plan_mutation,
            "jobAcknowledgement": job_acknowledgement,
            "jobPolling": job_polling,
            "groceryGeneration50Entries": grocery_generation,
            "suggestionSolve": suggestion_solve,
        }
        for name, operation in operations.items():
            runs = _measure(operation)
            report["paths"][name] = runs
            assert all(run["p95Ms"] < BUDGETS_MS[name] for run in runs), (name, runs)

    engine.dispose()
    report_path = Path(os.environ["COOKFULLY_PERFORMANCE_REPORT"])
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
