from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.planning_dates import week_date

from cookfully.api.main import create_app
from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.suggestions import SuggestionRun

WEEK_START = week_date(0)
NEXT_DAY = week_date(1)


def client_for(isolated_database_url: str, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=isolated_database_url,
                owner_email="owner@example.com",
                owner_bootstrap_password="correct horse battery staple",
                media_root=tmp_path / "media",
                export_root=tmp_path / "exports",
                erasure_ledger_root=tmp_path / "ledger",
            )
        )
    )


def authenticate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def seed_goal(client: TestClient, headers: dict[str, str]) -> None:
    response = client.put(
        "/api/v1/goals/current",
        headers=headers,
        json={
            "mode": "maintain",
            "maintenanceKcal": "500.000000",
            "caloriesKcal": "500.000000",
            "proteinG": "40.000000",
            "carbohydrateG": "50.000000",
            "fatG": "15.000000",
            "effectiveFrom": WEEK_START,
            "effectiveTo": None,
            "mealTargets": [],
        },
    )
    assert response.status_code == 200


def seed_recipe(client: TestClient, headers: dict[str, str], title: str, key: str) -> str:
    recipe = client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "title": title,
            "yieldQuantity": "2.000",
            "yieldUnit": "servings",
            "ingredients": [{"originalText": "100 g tofu"}],
            "instructions": [{"text": "Cook."}],
        },
    ).json()
    for index, (field, value) in enumerate(
        (
            ("calories_kcal", "250.000000"),
            ("protein_g", "20.000000"),
            ("carbohydrate_g", "25.000000"),
            ("fat_g", "7.500000"),
        )
    ):
        corrected = client.post(
            f"/api/v1/recipes/{recipe['id']}/nutrition/corrections",
            headers={**headers, "Idempotency-Key": f"{key}-correction-{index}"},
            json={"field": field, "decimalValue": value},
        )
        assert corrected.status_code == 201
    return recipe["id"]


def suggestion_payload(required: list[str]) -> dict[str, object]:
    return {
        "scope": "day",
        "weekStart": WEEK_START,
        "localDate": WEEK_START,
        "mealSlot": None,
        "tolerances": {
            "caloriesKcal": "0.000000",
            "proteinG": "0.000000",
            "carbohydrateG": "0.000000",
            "fatG": "0.000000",
        },
        "excludedRecipeIds": [],
        "requiredRecipeIds": required,
        "maxRecipeRepetitions": 2,
    }


def test_openapi_31_suggestion_create_status_result_and_acceptance_surface(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        schema = client.get("/api/openapi.json").json()
        assert schema["openapi"].startswith("3.1")
        assert {
            "/api/v1/suggestions",
            "/api/v1/suggestions/{suggestionId}",
            "/api/v1/suggestions/{suggestionId}/accept",
        }.issubset(schema["paths"])
        assert {
            "SuggestionRequest",
            "SuggestionResultResponse",
            "SuggestionAcceptanceRequest",
        }.issubset(schema["components"]["schemas"])


def test_exact_preview_partial_acceptance_parity_stale_plan_and_expiry(
    isolated_database_url: str, tmp_path: Path
) -> None:
    app = create_app(
        Settings(
            environment="test",
            database_url=isolated_database_url,
            owner_email="owner@example.com",
            owner_bootstrap_password="correct horse battery staple",
            media_root=tmp_path / "media",
            export_root=tmp_path / "exports",
            erasure_ledger_root=tmp_path / "ledger",
        )
    )
    with TestClient(app) as client:
        headers = authenticate(client)
        seed_goal(client, headers)
        first = seed_recipe(client, headers, "First exact bowl", "suggest-first")
        second = seed_recipe(client, headers, "Second exact bowl", "suggest-second")

        request_headers = {**headers, "Idempotency-Key": "suggestion-create-0001"}
        accepted = client.post(
            "/api/v1/suggestions",
            headers=request_headers,
            json=suggestion_payload([first, second]),
        )
        assert accepted.status_code == 202
        assert accepted.elapsed.total_seconds() < 1
        assert (
            client.post(
                "/api/v1/suggestions",
                headers=request_headers,
                json=suggestion_payload([first, second]),
            ).json()
            == accepted.json()
        )
        suggestion_id = UUID(accepted.json()["resourceId"])
        job_id = UUID(accepted.json()["jobId"])
        app.state.suggestions.run_job(job_id)

        progress = client.get(f"/api/v1/jobs/{job_id}")
        assert progress.status_code == 200 and progress.json()["status"] == "succeeded"
        result = client.get(f"/api/v1/suggestions/{suggestion_id}")
        assert result.status_code == 200
        body = result.json()
        assert body["status"] == "feasible"
        assert body["target"] == {
            "caloriesKcal": "500",
            "proteinG": "40",
            "carbohydrateG": "50",
            "fatG": "15",
        }
        assert body["objectiveScore"] == "0"
        assert body["unmetConstraintCount"] == 0
        assert body["distanceComponents"] == {
            "calories": "0",
            "protein": "0",
            "carbohydrates": "0",
            "fat": "0",
            "repetitionOverage": 0,
            "missingRequiredRecipes": 0,
        }
        assert len(body["items"]) == 2
        assert body["projectedWeekTotal"]["caloriesKcal"] == "500"
        assert body["planningNotice"] == "Planning aid only—not medical advice."

        selected = body["items"][0]
        accepted_plan = client.post(
            f"/api/v1/suggestions/{suggestion_id}/accept",
            headers={**headers, "Idempotency-Key": "suggestion-accept-0001"},
            json={"selectedItemIds": [selected["id"]], "expectedPlanVersion": 1},
        )
        assert accepted_plan.status_code == 200
        plan = accepted_plan.json()
        assert plan["version"] == 2
        assert plan["entries"][0]["origin"] == "suggestion"
        assert plan["weekTotal"]["caloriesKcal"] == selected["projectedNutrition"]["caloriesKcal"]
        assert plan["weekTotal"]["proteinG"] == selected["projectedNutrition"]["proteinG"]

        stale_accept = client.post(
            f"/api/v1/suggestions/{suggestion_id}/accept",
            headers={**headers, "Idempotency-Key": "suggestion-accept-stale"},
            json={"selectedItemIds": [body["items"][1]["id"]], "expectedPlanVersion": 1},
        )
        assert stale_accept.status_code == 409

        stale_request = client.post(
            "/api/v1/suggestions",
            headers={**headers, "Idempotency-Key": "suggestion-create-stale"},
            json=suggestion_payload([]),
        ).json()
        stale_suggestion_id = UUID(stale_request["resourceId"])
        stale_job_id = UUID(stale_request["jobId"])
        entry = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/entries",
            headers={**headers, "Idempotency-Key": "manual-plan-change"},
            json={
                "localDate": NEXT_DAY,
                "mealSlot": "lunch",
                "recipeId": first,
                "servings": "0.500",
                "position": 0,
                "refreshNutrition": False,
            },
        )
        assert entry.status_code == 201
        with pytest.raises(DomainError, match="meal plan changed"):
            app.state.suggestions.run_job(stale_job_id)
        stale_result = client.get(f"/api/v1/suggestions/{stale_suggestion_id}")
        assert stale_result.json()["failureCode"] == "stale_plan"

        with app.state.sessions.begin() as session:
            run = session.scalar(
                select(SuggestionRun).where(SuggestionRun.id == suggestion_id).with_for_update()
            )
            assert run is not None
            run.expires_at = utc_now() - timedelta(seconds=1)
        expired = client.get(f"/api/v1/suggestions/{suggestion_id}")
        assert expired.json()["status"] == "expired"
        expired_accept = client.post(
            f"/api/v1/suggestions/{suggestion_id}/accept",
            headers={**headers, "Idempotency-Key": "suggestion-accept-expired"},
            json={"selectedItemIds": [body["items"][1]["id"]], "expectedPlanVersion": 3},
        )
        assert expired_accept.status_code == 409
