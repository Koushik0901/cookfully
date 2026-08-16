from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.mcp.read_tools import ReadTools
from cookfully.mcp.resources import McpResources
from cookfully.mcp.write_tools import WriteTools

WEEK_START = "2026-03-09"


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


def seed_planning_state(client: TestClient, headers: dict[str, str]) -> dict[str, object]:
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
        headers=headers,
        json={
            "title": "MCP parity bowl",
            "yieldQuantity": "2.000",
            "yieldUnit": "servings",
            "ingredients": [{"originalText": "200 g tofu"}],
            "instructions": [{"text": "Cook."}],
        },
    ).json()
    for index, (field, value) in enumerate(
        (
            ("calories_kcal", "501.500000"),
            ("protein_g", "40.050000"),
            ("carbohydrate_g", "60.050000"),
            ("fat_g", "11.150000"),
        )
    ):
        response = client.post(
            f"/api/v1/recipes/{recipe['id']}/nutrition/corrections",
            headers={**headers, "Idempotency-Key": f"mcp-parity-correction-{index}"},
            json={"field": field, "decimalValue": value},
        )
        assert response.status_code == 201
    entry = client.post(
        f"/api/v1/meal-plans/{WEEK_START}/entries",
        headers={**headers, "Idempotency-Key": "mcp-parity-plan-entry"},
        json={
            "localDate": WEEK_START,
            "mealSlot": "breakfast",
            "recipeId": recipe["id"],
            "servings": "1.500",
            "position": 0,
            "refreshNutrition": False,
        },
    ).json()
    return {"goal": goal, "recipe": recipe, "entry": entry}


def owner_id(client: TestClient) -> UUID:
    with client.app.state.sessions() as session:
        owner = session.scalar(select(OwnerAccount))
        assert owner is not None
        return owner.id


def test_all_read_tools_and_resources_match_http_contract_exactly(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        seeded = seed_planning_state(client, headers)
        owner = owner_id(client)
        tools = ReadTools(
            client.app.state.goals,
            client.app.state.meal_plans,
            client.app.state.recipe_queries,
            client.app.state.suggestions,
            client.app.state.pantry,
        )

        goal_http = client.get("/api/v1/goals/current", params={"onDate": WEEK_START}).json()
        assert tools.get_current_goals(owner, on_date=WEEK_START) == goal_http

        plan_http = client.get(f"/api/v1/meal-plans/{WEEK_START}").json()
        plan_mcp = tools.get_meal_plan(owner, week_start=WEEK_START)
        assert plan_mcp == plan_http
        assert plan_mcp["entries"][0]["nutrition"]["caloriesKcal"] == "752"
        assert plan_mcp["entries"][0]["nutrition"]["status"] == "manual"
        assert isinstance(plan_mcp["entries"][0]["servings"], str)

        totals = tools.get_period_totals(
            owner,
            week_start=WEEK_START,
            local_date=WEEK_START,
            meal_slot="breakfast",
        )
        expected_meal_total = {
            **plan_http["dayTotals"][WEEK_START],
            "targetDifference": None,
        }
        assert totals == {
            "weekStart": WEEK_START,
            "localDate": WEEK_START,
            "mealSlot": "breakfast",
            "total": expected_meal_total,
            "entryIds": [seeded["entry"]["id"]],
        }

        recipes_http = client.get("/api/v1/recipes", params={"query": "parity"}).json()
        assert tools.find_recipes(owner, query="parity") == recipes_http

        resources = McpResources()
        methodology = resources.nutrition_methodology()
        assert "planning estimates" in methodology.lower()
        assert "correction" in methodology.lower() and "provenance" in methodology.lower()
        export_schema = resources.export_schema("v1")
        assert "decimal" in export_schema.lower() and "version" in export_schema.lower()


def test_all_write_tools_match_http_reloads_and_are_idempotent(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        seeded = seed_planning_state(client, headers)
        owner = owner_id(client)
        tools = WriteTools(
            client.app.state.meal_plans,
            client.app.state.grocery_lists,
            client.app.state.idempotency,
            client.app.state.suggestions,
            client.app.state.pantry,
        )
        recipe_id = str(seeded["recipe"]["id"])

        added = tools.add_recipe_to_plan(
            owner,
            recipe_id=recipe_id,
            week_start=WEEK_START,
            local_date="2026-03-10",
            meal_slot="lunch",
            servings="1.250",
            idempotency_key="mcp-add-entry-0001",
        )
        replay = tools.add_recipe_to_plan(
            owner,
            recipe_id=recipe_id,
            week_start=WEEK_START,
            local_date="2026-03-10",
            meal_slot="lunch",
            servings="1.250",
            idempotency_key="mcp-add-entry-0001",
        )
        assert replay == added
        plan = client.get(f"/api/v1/meal-plans/{WEEK_START}").json()
        assert added["entry"] == next(
            item for item in plan["entries"] if item["id"] == added["entry"]["id"]
        )
        assert added["dayTotal"] == plan["dayTotals"]["2026-03-10"]
        assert added["weekTotal"] == plan["weekTotal"]

        updated = tools.update_meal_plan_entry(
            owner,
            entry_id=added["entry"]["id"],
            local_date="2026-03-11",
            meal_slot="dinner",
            servings="2.000",
            expected_version=added["entry"]["version"],
            idempotency_key="mcp-update-entry-01",
            refresh_nutrition=False,
        )
        plan = client.get(f"/api/v1/meal-plans/{WEEK_START}").json()
        assert updated["entry"] == next(
            item for item in plan["entries"] if item["id"] == updated["entry"]["id"]
        )

        regenerated = tools.regenerate_grocery_list(
            owner,
            week_start=WEEK_START,
            idempotency_key="mcp-regenerate-list-01",
        )
        assert regenerated == client.get(f"/api/v1/meal-plans/{WEEK_START}/grocery-list").json()
        assert tools.get_grocery_list(owner, week_start=WEEK_START) == regenerated

        removed = tools.remove_meal_plan_entry(
            owner,
            entry_id=updated["entry"]["id"],
            expected_version=updated["entry"]["version"],
            idempotency_key="mcp-remove-entry-01",
        )
        replay_removed = tools.remove_meal_plan_entry(
            owner,
            entry_id=updated["entry"]["id"],
            expected_version=updated["entry"]["version"],
            idempotency_key="mcp-remove-entry-01",
        )
        assert replay_removed == removed
        reloaded = client.get(f"/api/v1/meal-plans/{WEEK_START}").json()
        assert removed["removed"] is True
        assert removed["weekTotal"] == reloaded["weekTotal"]
        assert all(item["id"] != updated["entry"]["id"] for item in reloaded["entries"])
