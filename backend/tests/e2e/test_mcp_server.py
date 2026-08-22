from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from tests.planning_dates import week_date

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings

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


def mcp_call(
    client: TestClient,
    secret: str,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: int = 1,
) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            **({"params": params} if params is not None else {}),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_streamable_http_tools_resources_scope_reload_and_exact_parity(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        goal = {
            "mode": "maintain",
            "maintenanceKcal": "2200",
            "caloriesKcal": "2200",
            "proteinG": "180",
            "carbohydrateG": "220",
            "fatG": "65",
            "effectiveFrom": "2026-03-01",
            "effectiveTo": None,
            "mealTargets": [],
        }
        assert client.put("/api/v1/goals/current", json=goal, headers=headers).status_code == 200
        recipe = client.post(
            "/api/v1/recipes",
            headers=headers,
            json={
                "title": "Inspector bowl",
                "yieldQuantity": "2.000",
                "yieldUnit": "servings",
                "ingredients": [{"originalText": "200 g tofu"}],
                "instructions": [{"text": "Cook."}],
            },
        ).json()
        for index, (field, value) in enumerate(
            (
                ("calories_kcal", "500"),
                ("protein_g", "40"),
                ("carbohydrate_g", "60"),
                ("fat_g", "10"),
            )
        ):
            assert (
                client.post(
                    f"/api/v1/recipes/{recipe['id']}/nutrition/corrections",
                    headers={**headers, "Idempotency-Key": f"mcp-e2e-correction-{index}"},
                    json={"field": field, "decimalValue": value},
                ).status_code
                == 201
            )

        read_token = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={
                "name": "Inspector read",
                "scopes": ["goals:read", "plans:read", "recipes:read"],
            },
        ).json()["secret"]
        write_token = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={"name": "Inspector write", "scopes": ["plans:read", "plans:write"]},
        ).json()["secret"]

        denied = client.post(
            "/mcp",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert denied.status_code == 401

        initialized = mcp_call(
            client,
            read_token,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "contract-inspector", "version": "1.0"},
            },
        )
        assert initialized["result"]["serverInfo"]["name"] == "Cookfully"
        listed = mcp_call(client, read_token, "tools/list", request_id=2)
        names = {tool["name"] for tool in listed["result"]["tools"]}
        assert {
            "get_current_goals",
            "get_meal_plan",
            "get_period_totals",
            "find_recipes",
            "add_recipe_to_plan",
            "update_meal_plan_entry",
            "remove_meal_plan_entry",
            "get_grocery_list",
            "regenerate_grocery_list",
            "request_suggestions",
            "get_suggestion_result",
            "list_pantry_items",
            "create_pantry_item",
            "update_pantry_item",
            "remove_pantry_item",
        } == names

        added = mcp_call(
            client,
            write_token,
            "tools/call",
            {
                "name": "add_recipe_to_plan",
                "arguments": {
                    "recipe_id": recipe["id"],
                    "week_start": WEEK_START,
                    "local_date": WEEK_START,
                    "meal_slot": "dinner",
                    "servings": "1.500",
                    "idempotency_key": "mcp-e2e-add-entry-01",
                },
            },
            request_id=3,
        )["result"]
        assert added["isError"] is False
        entry = added["structuredContent"]["entry"]
        assert entry["origin"] == "external"
        assert entry["nutrition"]["caloriesKcal"] == "750"
        assert isinstance(entry["servings"], str)

        reloaded_http = client.get(f"/api/v1/meal-plans/{WEEK_START}").json()
        assert entry == reloaded_http["entries"][0]
        read_plan = mcp_call(
            client,
            read_token,
            "tools/call",
            {"name": "get_meal_plan", "arguments": {"week_start": WEEK_START}},
            request_id=4,
        )["result"]["structuredContent"]
        assert read_plan == reloaded_http

        scope_denied = mcp_call(
            client,
            read_token,
            "tools/call",
            {
                "name": "add_recipe_to_plan",
                "arguments": {
                    "recipe_id": recipe["id"],
                    "week_start": WEEK_START,
                    "local_date": NEXT_DAY,
                    "meal_slot": "lunch",
                    "servings": "1",
                    "idempotency_key": "mcp-e2e-scope-denied",
                },
            },
            request_id=5,
        )["result"]
        assert scope_denied["isError"] is True
        assert scope_denied["structuredContent"]["error"]["code"] == "insufficient_scope"
        assert "insufficient_scope" in str(scope_denied)
        assert read_token not in str(scope_denied)

        resources = mcp_call(client, read_token, "resources/list", request_id=6)
        uris = {item["uri"] for item in resources["result"]["resources"]}
        assert "cookfully://methodology/nutrition" in uris
        templates = mcp_call(client, read_token, "resources/templates/list", request_id=7)
        template_uris = {item["uriTemplate"] for item in templates["result"]["resourceTemplates"]}
        assert "cookfully://schema/export/{version}" in template_uris
        methodology = mcp_call(
            client,
            read_token,
            "resources/read",
            {"uri": "cookfully://methodology/nutrition"},
            request_id=8,
        )
        assert "planning estimates" in methodology["result"]["contents"][0]["text"].lower()
        export_schema = mcp_call(
            client,
            read_token,
            "resources/read",
            {"uri": "cookfully://schema/export/v1"},
            request_id=9,
        )
        assert "decimal strings" in export_schema["result"]["contents"][0]["text"].lower()
        prompts = mcp_call(client, read_token, "prompts/list", request_id=10)
        assert prompts["result"]["prompts"] == []
