from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.planning_dates import week_date

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings

WEEK_START = week_date(0)
NEXT_DAY = week_date(1)
DAY_AFTER = week_date(2)


def client_for(isolated_database_url: str, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=isolated_database_url,
                owner_email="owner@example.com",
                owner_bootstrap_password="correct horse battery staple",
                media_root=tmp_path / "media",
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


def goal_payload() -> dict[str, object]:
    return {
        "mode": "cut",
        "maintenanceKcal": "2500.000000",
        "caloriesKcal": "2200.000000",
        "proteinG": "180.000000",
        "carbohydrateG": "220.000000",
        "fatG": "65.000000",
        "dietaryFiberG": "30.000000",
        "sodiumMg": "2000.000000",
        "effectiveFrom": "2026-03-01",
        "effectiveTo": None,
        "mealTargets": [
            {
                "mealSlot": "breakfast",
                "caloriesKcal": "500.000000",
                "proteinG": None,
                "carbohydrateG": "55.000000",
                "fatG": None,
            }
        ],
    }


def recipe_payload() -> dict[str, object]:
    return {
        "title": "Plan bowl",
        "yieldQuantity": "2.000",
        "yieldUnit": "servings",
        "ingredients": [{"originalText": "200 g tofu"}],
        "instructions": [{"text": "Cook."}],
    }


def unavailable_micronutrients() -> dict[str, object]:
    def value(unit: str, nutrient_id: int) -> dict[str, object]:
        return {
            "value": None,
            "unit": unit,
            "explicitZero": False,
            "coverageRatio": "0",
            "source": "unavailable",
            "mappingVersion": "usda-fdc-2026-04-v1",
            "usdaNutrientId": nutrient_id,
        }

    return {
        "dietaryFiberG": value("g", 1079),
        "sodiumMg": value("mg", 1093),
        "potassiumMg": value("mg", 1092),
        "calciumMg": value("mg", 1087),
        "ironMg": value("mg", 1089),
        "magnesiumMg": value("mg", 1090),
        "vitaminCMg": value("mg", 1162),
        "vitaminDUg": value("ug", 1114),
        "vitaminB12Ug": value("ug", 1178),
    }


def test_owner_preferences_goal_and_plan_openapi_surface(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        schema = client.get("/api/openapi.json").json()
        paths = schema["paths"]
        assert "/api/v1/goals/current" in paths
        assert "/api/v1/meal-plans/{weekStart}" in paths
        assert "/api/v1/meal-plans/{weekStart}/entries" in paths
        assert "/api/v1/meal-plan-entries/{entryId}" in paths
        assert {"UserGoalWriteRequest", "MealPlanResponse", "MealPlanEntryWriteRequest"}.issubset(
            schema["components"]["schemas"]
        )
        assert "goal" not in schema["components"]["schemas"]["MealPlanResponse"].get("required", [])


def test_required_goal_optional_meal_targets_preferences_and_canonical_decimals(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        preferences = client.get("/api/v1/owner/preferences")
        assert preferences.json() == {
            "displayName": "Owner",
            "timezone": "UTC",
            "weekStartsOn": 1,
            "healthProfile": {
                "ageYears": None,
                "heightCm": None,
                "currentWeightKg": None,
                "targetWeightKg": None,
                "dietaryPattern": "no_preference",
                "avoidIngredients": [],
            },
            "version": 1,
        }
        changed = client.put(
            "/api/v1/owner/preferences",
            json={
                "displayName": "Owner",
                "timezone": "America/Vancouver",
                "weekStartsOn": 7,
                "healthProfile": {
                    "currentWeightKg": 74.5,
                    "targetWeightKg": 70,
                    "dietaryPattern": "vegetarian",
                    "avoidIngredients": [" shellfish ", "peanuts"],
                },
                "version": 1,
            },
            headers=headers,
        )
        assert changed.status_code == 200
        assert changed.json()["weekStartsOn"] == 7
        assert changed.json()["healthProfile"] == {
            "ageYears": None,
            "heightCm": None,
            "currentWeightKg": 74.5,
            "targetWeightKg": 70,
            "dietaryPattern": "vegetarian",
            "avoidIngredients": ["shellfish", "peanuts"],
        }
        stale_preferences = client.put(
            "/api/v1/owner/preferences",
            json={"displayName": "Owner", "timezone": "UTC", "weekStartsOn": 1, "version": 1},
            headers=headers,
        )
        assert stale_preferences.status_code == 409

        missing_macro = goal_payload()
        missing_macro["proteinG"] = None
        rejected = client.put("/api/v1/goals/current", json=missing_macro, headers=headers)
        assert rejected.status_code == 422

        created = client.put("/api/v1/goals/current", json=goal_payload(), headers=headers)
        assert created.status_code == 200
        body = created.json()
        assert body["caloriesKcal"] == "2200"
        assert body["maintenanceKcal"] == "2500"
        assert body["proteinG"] == "180"
        assert body["dietaryFiberG"] == "30"
        assert body["sodiumMg"] == "2000"
        assert body["macroCalorieDifference"] == "-15"
        assert body["mealTargets"][0]["proteinG"] is None
        assert body["mealTargets"][0]["fatG"] is None
        current = client.get("/api/v1/goals/current", params={"onDate": "2026-03-08"})
        assert current.status_code == 200 and current.json() == body

        overlap = goal_payload()
        overlap["effectiveFrom"] = "2026-03-15"
        conflict = client.put("/api/v1/goals/current", json=overlap, headers=headers)
        assert conflict.status_code == 409


def test_meal_plan_crud_concurrency_and_decimal_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        client.put(
            "/api/v1/owner/preferences",
            json={
                "displayName": "Owner",
                "timezone": "America/Vancouver",
                "weekStartsOn": 1,
                "version": 1,
            },
            headers=headers,
        )
        assert (
            client.put("/api/v1/goals/current", json=goal_payload(), headers=headers).status_code
            == 200
        )
        recipe = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers).json()
        for index, (field, value) in enumerate(
            (
                ("calories_kcal", "501.500000"),
                ("protein_g", "40.050000"),
                ("carbohydrate_g", "60.050000"),
                ("fat_g", "11.150000"),
            )
        ):
            corrected = client.post(
                f"/api/v1/recipes/{recipe['id']}/nutrition/corrections",
                json={"field": field, "decimalValue": value},
                headers={**headers, "Idempotency-Key": f"plan-correction-{index:02d}"},
            )
            assert corrected.status_code == 201

        entry_payload = {
            "localDate": WEEK_START,
            "mealSlot": "breakfast",
            "recipeId": recipe["id"],
            "servings": "1.500",
            "position": 0,
            "refreshNutrition": False,
        }
        added = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/entries",
            json=entry_payload,
            headers={**headers, "Idempotency-Key": "plan-entry-add-0001"},
        )
        assert added.status_code == 201
        entry = added.json()
        assert entry["servings"] == "1.5"
        assert entry["nutrition"] == {
            "basisServings": "1.5",
            "caloriesKcal": "752",
            "proteinG": "60.1",
            "carbohydrateG": "90.1",
            "fatG": "16.7",
            "status": "manual",
            "coverageRatio": "0",
            "micronutrients": unavailable_micronutrients(),
        }

        plan = client.get(f"/api/v1/meal-plans/{WEEK_START}")
        assert plan.status_code == 200
        plan_body = plan.json()
        assert plan_body["timezone"] == "America/Vancouver"
        assert plan_body["weekTotal"]["caloriesKcal"] == "752"
        assert plan_body["dayTotals"][WEEK_START]["targetDifference"]["proteinG"] == "-119.9"

        moved_payload = {
            **entry_payload,
            "localDate": NEXT_DAY,
            "mealSlot": "lunch",
            "servings": "2.000",
        }
        moved = client.patch(
            f"/api/v1/meal-plan-entries/{entry['id']}",
            json=moved_payload,
            headers={**headers, "If-Match": '"1"', "Idempotency-Key": "plan-entry-move-001"},
        )
        assert moved.status_code == 200
        assert moved.json()["nutrition"]["caloriesKcal"] == "1003"
        stale = client.patch(
            f"/api/v1/meal-plan-entries/{entry['id']}",
            json=moved_payload,
            headers={**headers, "If-Match": '"1"', "Idempotency-Key": "plan-entry-stale-01"},
        )
        assert stale.status_code == 409

        copied = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/entries",
            json={**entry_payload, "localDate": DAY_AFTER, "position": 0},
            headers={**headers, "Idempotency-Key": "plan-entry-copy-0001"},
        )
        assert copied.status_code == 201
        removed = client.delete(
            f"/api/v1/meal-plan-entries/{copied.json()['id']}",
            headers={**headers, "If-Match": '"1"', "Idempotency-Key": "plan-entry-delete-01"},
        )
        assert removed.status_code == 204

        current_recipe = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        stale_recipe = client.patch(
            f"/api/v1/recipes/{recipe['id']}",
            json={**recipe_payload(), "title": "Plan bowl revised"},
            headers={**headers, "If-Match": f'"{current_recipe["version"]}"'},
        )
        assert stale_recipe.status_code == 200
        assert stale_recipe.json()["nutritionState"] == "stale"
        stale_add = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/entries",
            json={**entry_payload, "localDate": NEXT_DAY, "position": 1},
            headers={**headers, "Idempotency-Key": "plan-entry-stale-recipe-01"},
        )
        assert stale_add.status_code == 409
        assert stale_add.json()["code"] == "recipe_nutrition_stale"


def test_meal_plan_can_start_before_a_goal_exists(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers).json()
        for index, (field, value) in enumerate(
            (
                ("calories_kcal", "501.500000"),
                ("protein_g", "40.050000"),
                ("carbohydrate_g", "60.050000"),
                ("fat_g", "11.150000"),
            )
        ):
            corrected = client.post(
                f"/api/v1/recipes/{recipe['id']}/nutrition/corrections",
                json={"field": field, "decimalValue": value},
                headers={**headers, "Idempotency-Key": f"goal-free-correction-{index:02d}"},
            )
            assert corrected.status_code == 201

        added = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/entries",
            json={
                "localDate": WEEK_START,
                "mealSlot": "dinner",
                "recipeId": recipe["id"],
                "servings": "1.500",
                "position": 0,
                "refreshNutrition": False,
            },
            headers={**headers, "Idempotency-Key": "goal-free-plan-entry-01"},
        )
        assert added.status_code == 201

        plan = client.get(f"/api/v1/meal-plans/{WEEK_START}")
        assert plan.status_code == 200
        body = plan.json()
        assert body["goal"] is None
        assert body["entries"][0]["recipeTitle"] == "Plan bowl"
        assert body["dayTotals"][WEEK_START]["targetDifference"] is None
