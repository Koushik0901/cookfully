from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings


def recipe_payload(title: str = "Weeknight lentils") -> dict[str, object]:
    return {
        "title": title,
        "description": "A simple dinner.",
        "yieldQuantity": "2.000",
        "yieldUnit": "servings",
        "ingredients": [
            {
                "originalText": "200 g lentils",
                "quantityMin": "200.000000",
                "quantityMax": "200.000000",
                "unit": "gram",
                "food": "lentils",
            }
        ],
        "instructions": [{"text": "Cook the lentils."}],
    }


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
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 204
    csrf = client.cookies.get("cookfully_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


def test_recipe_organization_contract_covers_filters_collections_and_conflicts(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers).json()
        first = client.post(
            "/api/v1/recipes/collections", json={"name": "Weeknight"}, headers=headers
        )
        second = client.post(
            "/api/v1/recipes/collections", json={"name": "Favourites"}, headers=headers
        )
        assert first.status_code == 201
        assert second.status_code == 201
        first_collection = first.json()
        second_collection = second.json()

        duplicate = client.post(
            "/api/v1/recipes/collections", json={"name": "Weeknight"}, headers=headers
        )
        assert duplicate.status_code == 409

        reordered = client.patch(
            f"/api/v1/recipes/collections/{second_collection['id']}",
            json={"position": 0},
            headers={**headers, "If-Match": '"1"'},
        )
        assert reordered.status_code == 200
        assert reordered.json()["position"] == 0
        assert reordered.json()["version"] == 2
        renamed = client.patch(
            f"/api/v1/recipes/collections/{first_collection['id']}",
            json={"name": "Weeknight meals"},
            headers={**headers, "If-Match": '"1"'},
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Weeknight meals"
        collections = client.get("/api/v1/recipes/collections", headers=headers)
        assert [(item["name"], item["position"]) for item in collections.json()] == [
            ("Favourites", 0),
            ("Weeknight meals", 1),
        ]

        invalid_role = client.put(
            f"/api/v1/recipes/{recipe['id']}/organization",
            json={"favorite": True, "collectionIds": [], "mealRoles": ["brunch"]},
            headers={**headers, "If-Match": '"1"'},
        )
        assert invalid_role.status_code == 422
        duplicate_collection = client.put(
            f"/api/v1/recipes/{recipe['id']}/organization",
            json={
                "favorite": True,
                "collectionIds": [first_collection["id"], first_collection["id"]],
                "mealRoles": [],
            },
            headers={**headers, "If-Match": '"1"'},
        )
        assert duplicate_collection.status_code == 422

        organized = client.put(
            f"/api/v1/recipes/{recipe['id']}/organization",
            json={
                "favorite": True,
                "collectionIds": [first_collection["id"], second_collection["id"]],
                "mealRoles": ["dinner", "snack"],
            },
            headers={**headers, "If-Match": '"1"'},
        )
        assert organized.status_code == 200
        assert organized.json()["favorite"] is True
        assert {item["name"] for item in organized.json()["collections"]} == {
            "Weeknight meals",
            "Favourites",
        }
        assert organized.json()["mealRoles"] == ["dinner", "snack"]
        assert organized.json()["version"] == 2

        for params in (
            {"favorite": True},
            {"collectionId": first_collection["id"]},
            {"mealRole": "dinner"},
        ):
            filtered = client.get("/api/v1/recipes", params=params, headers=headers)
            assert filtered.status_code == 200
            assert [item["id"] for item in filtered.json()["items"]] == [recipe["id"]]

        stale_recipe = client.put(
            f"/api/v1/recipes/{recipe['id']}/organization",
            json={"favorite": False, "collectionIds": [], "mealRoles": []},
            headers={**headers, "If-Match": '"1"'},
        )
        assert stale_recipe.status_code == 409
        stale_collection = client.patch(
            f"/api/v1/recipes/collections/{second_collection['id']}",
            json={"name": "Saved"},
            headers={**headers, "If-Match": '"1"'},
        )
        assert stale_collection.status_code == 409

        foreign_collection = client.put(
            f"/api/v1/recipes/{recipe['id']}/organization",
            json={"favorite": True, "collectionIds": [str(uuid4())], "mealRoles": []},
            headers={**headers, "If-Match": '"2"'},
        )
        assert foreign_collection.status_code == 404

        deleted = client.delete(
            f"/api/v1/recipes/collections/{first_collection['id']}",
            headers={**headers, "If-Match": '"2"'},
        )
        assert deleted.status_code == 204
        remaining = client.get(f"/api/v1/recipes/{recipe['id']}", headers=headers)
        assert [item["name"] for item in remaining.json()["collections"]] == ["Favourites"]
