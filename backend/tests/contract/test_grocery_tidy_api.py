from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_meal_plan_api import WEEK_START, authenticate, client_for, goal_payload
from tests.unit.test_grocery_tidy import _merge_responder

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.grocery_lists import GroceryListService
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore


def _responder(model: str, state: Any, questions: Any) -> object:
    if "same" in questions:
        return _merge_responder(model, state, questions)
    salt = "salt" in state["grocery_item"]
    return {
        "aisle": {
            "type": "choice",
            "probabilities": {"spices" if salt else "produce": 0.9, "other": 0.1},
        },
        "staple": {"type": "noul", "noul": 0.95 if salt else 0.05},
    }


def test_grocery_list_merges_labels_and_honours_overrides(
    isolated_database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = Decisions(
        DecisionsConfig("k", features={Purpose.GROCERY_TIDY: FeatureConfig(True, ("m1", "m2"))}),
        ScriptedDecisionTransport(_responder),
        InMemoryDecisionStore(),
    )
    monkeypatch.setattr(GroceryListService, "_tidy_engine", lambda _self: engine)
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        assert (
            client.put("/api/v1/goals/current", json=goal_payload(), headers=headers).status_code
            == 200
        )
        for index, lines in enumerate((["3 scallions", "1 tsp salt"], ["2 green onions"])):
            recipe = client.post(
                "/api/v1/recipes",
                json={
                    "title": f"Dish {index}",
                    "yieldQuantity": "1.000",
                    "yieldUnit": "servings",
                    "ingredients": [{"originalText": line} for line in lines],
                    "instructions": [{"text": "Cook."}],
                },
                headers=headers,
            ).json()
            added = client.post(
                f"/api/v1/meal-plans/{WEEK_START}/entries",
                json={
                    "localDate": WEEK_START,
                    "mealSlot": "dinner",
                    "recipeId": recipe["id"],
                    "servings": "1.000",
                    "position": index,
                    "refreshNutrition": False,
                },
                headers={**headers, "Idempotency-Key": f"grocery-tidy-entry-{index:04d}"},
            )
            assert added.status_code == 201, added.text

        generated = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list",
            headers={**headers, "Idempotency-Key": "grocery-tidy-generate-0001"},
        )
        assert generated.status_code == 200, generated.text
        items = {item["displayName"]: item for item in generated.json()["items"]}
        merged = [item for item in items.values() if item["mergedFrom"]]
        assert len(merged) == 1, items
        assert len(merged[0]["mergedFrom"]) == 1
        assert "scallion" in merged[0]["mergedFrom"][0]
        assert merged[0]["aisle"] == "produce"
        salt = next(item for name, item in items.items() if "salt" in name)
        assert salt["aisle"] == "spices" and salt["likelyStaple"] is True

        # Owner override persists across regeneration.
        changed = client.patch(
            f"/api/v1/grocery-items/{salt['id']}",
            json={"likelyStaple": False, "aisle": "pantry"},
            headers={
                **headers,
                "If-Match": f'"{salt["version"]}"',
                "Idempotency-Key": "grocery-tidy-salt-00001",
            },
        )
        assert changed.status_code == 200, changed.text
        regenerated = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list",
            headers={**headers, "Idempotency-Key": "grocery-tidy-generate-0002"},
        ).json()
        salt_again = next(item for item in regenerated["items"] if "salt" in item["displayName"])
        assert (salt_again["aisle"], salt_again["likelyStaple"]) == ("pantry", False)

        # Keep separate undoes the merge for good.
        current = client.get(f"/api/v1/meal-plans/{WEEK_START}/grocery-list").json()
        # The regenerate response must not list rows it deleted.
        assert [i["id"] for i in regenerated["items"]] == [i["id"] for i in current["items"]]
        merged_now = next(item for item in current["items"] if item["mergedFrom"])
        separated = client.post(
            f"/api/v1/grocery-items/{merged_now['id']}/keep-separate", headers=headers
        )
        assert separated.status_code == 200, separated.text
        names = sorted(item["displayName"] for item in separated.json()["items"])
        assert len([n for n in names if "onion" in n or "scallion" in n]) == 2
        assert all(not item["mergedFrom"] for item in separated.json()["items"])


def test_warming_the_shelf_life_answer_never_breaks_a_check_off(
    isolated_database_url: str, tmp_path: Path
) -> None:
    from uuid import uuid4

    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        service = client.app.state.grocery_lists
        with client.app.state.sessions() as session:
            from sqlalchemy import select

            from cookfully.infrastructure.models.identity import OwnerAccount

            owner = session.scalar(select(OwnerAccount.id).limit(1))
        assert owner is not None
        # An unknown item makes the lookup fail; the warm-up logs it and carries on.
        service._warm_expiry_answer(owner, uuid4(), {"checked": True})
        # Nothing to warm when the item is not being checked off.
        service._warm_expiry_answer(owner, uuid4(), {"checked": False})
