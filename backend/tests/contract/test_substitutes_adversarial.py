"""Substitutes route: malformed ids, other recipes' ingredients, anonymous callers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from tests.contract.test_meal_plan_api import authenticate, client_for


def _recipe(client: Any, headers: dict[str, str], title: str, lines: list[str]) -> dict[str, Any]:
    created = client.post(
        "/api/v1/recipes",
        json={
            "title": title,
            "yieldQuantity": "2.000",
            "yieldUnit": "servings",
            "ingredients": [{"originalText": line} for line in lines],
            "instructions": [{"text": "Cook."}],
        },
        headers=headers,
    ).json()
    return client.get(f"/api/v1/recipes/{created['id']}").json()


@pytest.mark.parametrize(
    "bad",
    ["not-a-uuid", "123", "00000000-0000-0000-0000-00000000000g", "%27%3BDROP%20TABLE", "a" * 300],
)
def test_malformed_ids_are_refused_cleanly(
    isolated_database_url: str, tmp_path: Path, bad: str
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = _recipe(client, headers, "Pancakes", ["1 cup buttermilk"])
        response = client.get(f"/api/v1/recipes/{recipe['id']}/ingredients/{bad}/substitutes")
        assert response.status_code in (404, 422)
        response = client.get(f"/api/v1/recipes/{bad}/ingredients/{uuid4()}/substitutes")
        assert response.status_code in (404, 422)
        assert client.get(f"/api/v1/recipes/{recipe['id']}").status_code == 200


def test_an_ingredient_of_a_different_recipe_is_not_found_under_this_one(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        first = _recipe(client, headers, "Pancakes", ["1 cup buttermilk"])
        second = _recipe(client, headers, "Waffles", ["1 cup butter"])
        foreign = second["ingredients"][0]["id"]
        response = client.get(f"/api/v1/recipes/{first['id']}/ingredients/{foreign}/substitutes")
        assert response.status_code == 404


def test_anonymous_callers_get_nothing(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as owner:
        headers = authenticate(owner)
        recipe = _recipe(owner, headers, "Pancakes", ["1 cup buttermilk"])
        ingredient = recipe["ingredients"][0]["id"]
    with client_for(isolated_database_url, tmp_path) as anonymous:
        response = anonymous.get(
            f"/api/v1/recipes/{recipe['id']}/ingredients/{ingredient}/substitutes"
        )
        assert response.status_code in (401, 403)
        assert "buttermilk" not in response.text.lower()


@pytest.mark.parametrize(
    "line",
    [
        "1 cup BUTTERMILK",
        "1 cup buttermilk (or milk + lemon)",
        "½ cup buttermilk",
        "buttermilk",
        "2 cups homemade vegan buttermilk",
        "1 tbsp butter",
        "1 stick unsalted butter, softened",
        "",
        "   ",
    ],
)
def test_odd_ingredient_lines_never_break_the_route(
    isolated_database_url: str, tmp_path: Path, line: str
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = _recipe(client, headers, "Test", [line or "1 cup water"])
        ingredient = recipe["ingredients"][0]["id"]
        response = client.get(
            f"/api/v1/recipes/{recipe['id']}/ingredients/{ingredient}/substitutes"
        )
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["substitutes"], list)
        assert body["ranked"] is False  # no key in this test database


def test_the_substitutes_route_is_get_only_and_needs_no_csrf_to_read(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = _recipe(client, headers, "Pancakes", ["1 cup buttermilk"])
        ingredient = recipe["ingredients"][0]["id"]
        url = f"/api/v1/recipes/{recipe['id']}/ingredients/{ingredient}/substitutes"
        for method in ("post", "put", "delete", "patch"):
            response = getattr(client, method)(url, headers=headers)
            assert response.status_code in (404, 405), method
