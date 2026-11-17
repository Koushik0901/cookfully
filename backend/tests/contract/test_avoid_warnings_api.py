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


def test_hidden_ingredient_warnings_are_stored_and_go_stale_with_the_list(
    isolated_database_url: str, tmp_path: Path
) -> None:
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
    from cookfully.application.hidden_ingredients import refresh_hidden_ingredients
    from cookfully.domain.decisions import Purpose
    from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
    from cookfully.infrastructure.decision_store import InMemoryDecisionStore

    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post(
            "/api/v1/recipes",
            json={
                "title": "Caesar salad",
                "yieldQuantity": "2.000",
                "yieldUnit": "servings",
                "ingredients": [
                    {"originalText": "1 head romaine"},
                    {"originalText": "1 tbsp Worcestershire sauce"},
                ],
                "instructions": [{"text": "Toss."}],
            },
            headers=headers,
        ).json()
        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        assert detail["hiddenIngredientCheck"] == "no_avoid_list"

        _set_avoid(client, headers, ["fish"])
        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        # No OpenRouter key here: the background recheck could not run, so it is not "safe".
        assert detail["hiddenIngredientCheck"] == "not_checked"
        assert detail["avoidWarnings"] == []

        def responder(_model: str, state: dict[str, str], _questions: object) -> object:
            suspect = "Worcestershire" in state["ingredient_line"]
            return {"a0": {"type": "noul", "noul": 0.92 if suspect else 0.03}}

        engine = create_engine(isolated_database_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        decisions = Decisions(
            DecisionsConfig(
                "k",
                features={
                    Purpose.HIDDEN_INGREDIENTS: FeatureConfig(
                        True, ("typesafe/jev-1.14", "cloudflare/clef")
                    )
                },
            ),
            ScriptedDecisionTransport(responder),
            InMemoryDecisionStore(),
        )
        status = refresh_hidden_ingredients(factory, UUID(recipe["id"]), decisions=decisions)
        assert status == "checked"
        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        assert detail["hiddenIngredientCheck"] == "checked"
        lines = {item["id"]: item["originalText"] for item in detail["ingredients"]}
        [warning] = detail["avoidWarnings"]
        assert lines[warning["ingredientId"]] == "1 tbsp Worcestershire sauce"
        assert (warning["item"], warning["source"]) == ("fish", "model")
        assert Decimal(warning["probability"]) == Decimal("0.92")

        # A second refresh with nothing changed is a no-op.
        assert refresh_hidden_ingredients(factory, UUID(recipe["id"]), decisions=decisions) == (
            "checked"
        )

        # Changing the list makes the stored result stale until it is rechecked.
        _set_avoid(client, headers, ["fish", "dairy"])
        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        assert detail["hiddenIngredientCheck"] == "not_checked"
        assert detail["avoidWarnings"] == []
        engine.dispose()
