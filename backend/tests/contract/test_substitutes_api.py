from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from tests.contract.test_meal_plan_api import authenticate, client_for


def test_substitutes_route_returns_table_swaps_unranked_without_a_key(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post(
            "/api/v1/recipes",
            json={
                "title": "Pancakes",
                "yieldQuantity": "2.000",
                "yieldUnit": "servings",
                "ingredients": [
                    {"originalText": "1 cup buttermilk"},
                    {"originalText": "1 tsp salt"},
                ],
                "instructions": [{"text": "Whisk and fry."}],
            },
            headers=headers,
        ).json()
        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        by_text = {item["originalText"]: item for item in detail["ingredients"]}
        assert by_text["1 cup buttermilk"]["substitutable"] is True
        assert by_text["1 tsp salt"]["substitutable"] is False

        buttermilk = by_text["1 cup buttermilk"]["id"]
        body = client.get(
            f"/api/v1/recipes/{recipe['id']}/ingredients/{buttermilk}/substitutes"
        ).json()
        assert body["ranked"] is False
        assert body["originalText"] == "1 cup buttermilk"
        assert body["substitutes"][0]["name"] == "Milk with lemon juice or vinegar"
        assert body["substitutes"][0]["probability"] is None

        salt = by_text["1 tsp salt"]["id"]
        empty = client.get(f"/api/v1/recipes/{recipe['id']}/ingredients/{salt}/substitutes")
        assert empty.json()["substitutes"] == []
        missing = client.get(f"/api/v1/recipes/{recipe['id']}/ingredients/{uuid4()}/substitutes")
        assert missing.status_code == 404
