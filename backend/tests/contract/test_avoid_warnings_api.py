from __future__ import annotations

from pathlib import Path

from tests.contract.test_meal_plan_api import (
    WEEK_START,
    authenticate,
    client_for,
    goal_payload,
)


def _set_avoid(client, headers, items: list[str]) -> None:  # type: ignore[no-untyped-def]
    current = client.get("/api/v1/owner/preferences").json()
    response = client.put(
        "/api/v1/owner/preferences",
        json={
            "displayName": current["displayName"],
            "timezone": current["timezone"],
            "weekStartsOn": current["weekStartsOn"],
            "healthProfile": {**current["healthProfile"], "avoidIngredients": items},
            "version": current["version"],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text


def test_recipe_detail_and_plan_warn_about_avoided_ingredients(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post(
            "/api/v1/recipes",
            json={
                "title": "Pad thai",
                "yieldQuantity": "2.000",
                "yieldUnit": "servings",
                "ingredients": [
                    {"originalText": "200 g rice noodles"},
                    {"originalText": "150 g shrimp, peeled"},
                    {"originalText": "3 tbsp roasted peanuts"},
                ],
                "instructions": [{"text": "Stir-fry."}],
            },
            headers=headers,
        ).json()
        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        assert detail["avoidWarnings"] == []

        _set_avoid(client, headers, ["shellfish", "peanuts"])
        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        by_line = {item["id"]: item["originalText"] for item in detail["ingredients"]}
        warnings = [
            (by_line[warning["ingredientId"]], warning["item"], warning["source"])
            for warning in detail["avoidWarnings"]
        ]
        assert warnings == [
            ("150 g shrimp, peeled", "shellfish", "ingredient"),
            ("3 tbsp roasted peanuts", "peanuts", "ingredient"),
        ]

        assert (
            client.put("/api/v1/goals/current", json=goal_payload(), headers=headers).status_code
            == 200
        )
        added = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/entries",
            json={
                "localDate": WEEK_START,
                "mealSlot": "dinner",
                "recipeId": recipe["id"],
                "servings": "1.000",
                "position": 0,
                "refreshNutrition": False,
            },
            headers={**headers, "Idempotency-Key": "avoid-plan-entry-0001"},
        )
        assert added.status_code == 201, added.text
        plan = client.get(f"/api/v1/meal-plans/{WEEK_START}").json()
        assert plan["avoidWarnings"] == [
            {"recipeId": recipe["id"], "items": ["shellfish", "peanuts"]}
        ]

        # Changing the list changes the warnings at once; nothing is stored.
        _set_avoid(client, headers, ["cilantro"])
        assert client.get(f"/api/v1/recipes/{recipe['id']}").json()["avoidWarnings"] == []
        assert client.get(f"/api/v1/meal-plans/{WEEK_START}").json()["avoidWarnings"] == []
