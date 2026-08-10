from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from vigor_vine.api.main import create_app
from vigor_vine.infrastructure.config import Settings


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
    return {"X-CSRF-Token": client.cookies["vv_csrf"]}


def test_pantry_openapi_and_exact_decimal_crud(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        paths = client.get("/api/openapi.json").json()["paths"]
        assert "/api/v1/pantry-items" in paths
        assert "/api/v1/pantry-items/{itemId}" in paths
        assert "/api/v1/pantry/recipe-matches" in paths
        assert "/api/v1/meal-plans/{weekStart}/grocery-list/pantry-deductions" in paths
        assert "/api/v1/pantry-deductions/{deductionId}" in paths

        headers = authenticate(client)
        created = client.post(
            "/api/v1/pantry-items",
            json={"displayName": "Brown rice", "quantity": "0.250000", "unit": "kg"},
            headers={**headers, "Idempotency-Key": "pantry-create-0001"},
        )
        assert created.status_code == 201
        assert created.json()["quantity"] == "0.25"
        assert created.json()["normalizedFoodName"] == "brown rice"
        assert created.json()["matchStatus"] in {"unmatched", "proposed", "matched", "manual"}

        numeric = client.post(
            "/api/v1/pantry-items",
            json={"displayName": "Beans", "quantity": 1.25, "unit": "kg"},
            headers={**headers, "Idempotency-Key": "pantry-number-0001"},
        )
        assert numeric.status_code == 422

        item = created.json()
        changed = client.patch(
            f"/api/v1/pantry-items/{item['id']}",
            json={
                "displayName": item["displayName"],
                "quantity": "0.333333",
                "unit": "kg",
                "foodReferenceId": None,
            },
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "pantry-change-0001",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["quantity"] == "0.333333"

        stale = client.patch(
            f"/api/v1/pantry-items/{item['id']}",
            json={
                "displayName": item["displayName"],
                "quantity": "0.5",
                "unit": "kg",
                "foodReferenceId": None,
            },
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "pantry-stale-0001",
            },
        )
        assert stale.status_code == 409
