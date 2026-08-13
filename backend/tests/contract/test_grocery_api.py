from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.recipes import Ingredient


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


def seed_plan(
    client: TestClient, isolated_database_url: str, headers: dict[str, str]
) -> dict[str, object]:
    goal = {
        "mode": "maintain",
        "maintenanceKcal": "2200.000000",
        "caloriesKcal": "2200.000000",
        "proteinG": "180.000000",
        "carbohydrateG": "220.000000",
        "fatG": "65.000000",
        "effectiveFrom": "2026-03-01",
        "effectiveTo": None,
        "mealTargets": [],
    }
    assert client.put("/api/v1/goals/current", json=goal, headers=headers).status_code == 200
    recipe = client.post(
        "/api/v1/recipes",
        json={
            "title": "Grocery bowl",
            "yieldQuantity": "2.000",
            "yieldUnit": "servings",
            "ingredients": [{"originalText": "200 g red onion"}],
            "instructions": ["Cook."],
        },
        headers=headers,
    ).json()
    engine = create_engine(isolated_database_url)
    with Session(engine) as session, session.begin():
        ingredient = session.scalar(select(Ingredient).where(Ingredient.recipe_id == recipe["id"]))
        assert ingredient is not None
        ingredient.quantity_min = 200
        ingredient.quantity_max = 200
        ingredient.unit_code = "g"
        ingredient.unit_text = "g"
        ingredient.food_name = "red onion"
        ingredient.parse_status = "parsed"
    engine.dispose()
    for index, (field, value) in enumerate(
        (
            ("calories_kcal", "500"),
            ("protein_g", "40"),
            ("carbohydrate_g", "60"),
            ("fat_g", "10"),
        )
    ):
        response = client.post(
            f"/api/v1/recipes/{recipe['id']}/nutrition/corrections",
            json={"field": field, "decimalValue": value},
            headers={**headers, "Idempotency-Key": f"grocery-correction-{index}"},
        )
        assert response.status_code == 201
    added = client.post(
        "/api/v1/meal-plans/2026-03-09/entries",
        json={
            "localDate": "2026-03-09",
            "mealSlot": "dinner",
            "recipeId": recipe["id"],
            "servings": "1.500",
            "position": 0,
            "refreshNutrition": False,
        },
        headers={**headers, "Idempotency-Key": "grocery-plan-entry"},
    )
    assert added.status_code == 201
    return {"recipe": recipe, "entry": added.json()}


def test_grocery_openapi_surface(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        paths = client.get("/api/openapi.json").json()["paths"]
        assert "/api/v1/meal-plans/{weekStart}/grocery-list" in paths
        assert "/api/v1/meal-plans/{weekStart}/grocery-list/items" in paths
        assert "/api/v1/grocery-items/{itemId}" in paths


def test_generation_manual_crud_regeneration_decimals_and_concurrency(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        seeded = seed_plan(client, isolated_database_url, headers)
        generated = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list",
            headers={**headers, "Idempotency-Key": "grocery-generate-1"},
        )
        assert generated.status_code == 200
        body = generated.json()
        assert body["status"] == "current"
        assert body["items"][0]["quantity"] == "150"
        assert body["items"][0]["unit"] == "g"
        assert body["items"][0]["sources"] == [
            {
                "mealPlanEntryId": seeded["entry"]["id"],
                "originalText": "200 g red onion",
                "quantityContribution": "150",
            }
        ]
        assert client.get("/api/v1/meal-plans/2026-03-09/grocery-list").json() == body

        empty = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list/items",
            json={"displayName": ""},
            headers={**headers, "Idempotency-Key": "manual-empty-0001"},
        )
        assert empty.status_code == 422
        assert empty.headers["content-type"].startswith("application/problem+json")

        manual = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list/items",
            json={"displayName": "Reusable bags", "quantity": "2.000000", "unit": "bags"},
            headers={**headers, "Idempotency-Key": "manual-create-001"},
        )
        assert manual.status_code == 201
        assert manual.json()["quantity"] == "2"
        item = body["items"][0]
        changed = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"displayName": "My onions", "checked": True},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "grocery-edit-0001",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["checked"] is True
        assert changed.json()["displayName"] == "My onions"
        stale = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"checked": False},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "grocery-edit-stale",
            },
        )
        assert stale.status_code == 409

        entry = seeded["entry"]
        moved = client.patch(
            f"/api/v1/meal-plan-entries/{entry['id']}",
            json={
                "localDate": entry["localDate"],
                "mealSlot": entry["mealSlot"],
                "recipeId": seeded["recipe"]["id"],
                "servings": "2.000",
                "position": entry["position"],
                "refreshNutrition": False,
            },
            headers={
                **headers,
                "If-Match": f'"{entry["version"]}"',
                "Idempotency-Key": "grocery-plan-resize",
            },
        )
        assert moved.status_code == 200
        assert client.get("/api/v1/meal-plans/2026-03-09").json()["groceryStatus"] == "dirty"
        regenerated = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list",
            headers={**headers, "Idempotency-Key": "grocery-generate-2"},
        )
        generated_item = next(
            value for value in regenerated.json()["items"] if value["origin"] == "generated"
        )
        assert generated_item["quantity"] == "200"
        assert generated_item["checked"] is True
        assert generated_item["displayName"] == "My onions"

        removed = client.delete(
            f"/api/v1/grocery-items/{manual.json()['id']}",
            headers={
                **headers,
                "If-Match": f'"{manual.json()["version"]}"',
                "Idempotency-Key": "manual-delete-001",
            },
        )
        assert removed.status_code == 204


def test_grocery_rejects_numeric_json_and_bad_versions(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        seed_plan(client, isolated_database_url, headers)
        invalid = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list/items",
            json={"displayName": "Fruit", "quantity": 2.5},
            headers={**headers, "Idempotency-Key": "manual-number-001"},
        )
        assert invalid.status_code == 422
        missing_version = client.patch(
            "/api/v1/grocery-items/00000000-0000-4000-8000-000000000001",
            json={"checked": True},
            headers={**headers, "Idempotency-Key": "missing-version-01"},
        )
        assert missing_version.status_code == 428


def test_shopping_stops_placements_and_completed_pass_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        seed_plan(client, isolated_database_url, headers)
        grocery = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list",
            headers={**headers, "Idempotency-Key": "grocery-stops-generate"},
        ).json()
        first = client.post(
            "/api/v1/grocery-shopping-stops", json={"name": "Market"}, headers=headers
        )
        second = client.post(
            "/api/v1/grocery-shopping-stops", json={"name": "Bakery"}, headers=headers
        )
        assert first.status_code == second.status_code == 201
        assert [value["name"] for value in client.get("/api/v1/grocery-shopping-stops").json()] == [
            "Market",
            "Bakery",
        ]

        item = grocery["items"][0]
        assigned = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"shoppingStopId": first.json()["id"], "checked": True},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "grocery-stop-place-01",
            },
        )
        assert assigned.status_code == 200
        assert assigned.json()["shoppingStop"]["name"] == "Market"

        current = client.get("/api/v1/meal-plans/2026-03-09/grocery-list").json()
        completed = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list/complete",
            headers={**headers, "If-Match": f'"{current["version"]}"'},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["completedAt"] is not None

        completed_item = completed.json()["items"][0]
        blocked_edit = client.patch(
            f"/api/v1/grocery-items/{completed_item['id']}",
            json={"checked": False},
            headers={
                **headers,
                "If-Match": f'"{completed_item["version"]}"',
                "Idempotency-Key": "grocery-completed-edit",
            },
        )
        assert blocked_edit.status_code == 409
        reopened = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list/reopen",
            headers={**headers, "If-Match": f'"{completed.json()["version"]}"'},
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "current"
