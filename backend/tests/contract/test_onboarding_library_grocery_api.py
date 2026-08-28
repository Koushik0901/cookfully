from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from tests.contract.test_grocery_api import WEEK_START, seed_plan

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings


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


def test_onboarding_contract_transitions_and_version_conflicts(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        pending = client.get("/api/v1/owner/onboarding", headers=headers)
        assert pending.status_code == 200
        assert pending.json()["state"] == "pending"
        assert pending.json()["version"] == 1

        invalid = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={"state": "pending", "version": 1},
        )
        assert invalid.status_code == 422

        resolved = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={"state": "dismissed", "version": 1},
        )
        assert resolved.status_code == 200
        assert resolved.json()["state"] == "dismissed"
        assert resolved.json()["version"] == 2

        stale = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={"state": "completed", "version": 1},
        )
        assert stale.status_code == 409


def test_grocery_stop_placement_completion_and_reopen_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        seeded = seed_plan(client, isolated_database_url, headers)
        grocery = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list",
            headers={**headers, "Idempotency-Key": "contract-grocery-generate"},
        )
        assert grocery.status_code == 200
        item = grocery.json()["items"][0]

        stop = client.post(
            "/api/v1/grocery-shopping-stops",
            json={"name": "Market"},
            headers=headers,
        )
        assert stop.status_code == 201
        assert client.get("/api/v1/grocery-shopping-stops", headers=headers).json()[0]["name"] == (
            "Market"
        )

        assigned = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"shoppingStopId": stop.json()["id"], "checked": True},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "contract-grocery-place",
            },
        )
        assert assigned.status_code == 200
        assert assigned.json()["shoppingStop"]["id"] == stop.json()["id"]

        current = client.get(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list", headers=headers
        ).json()
        completed = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list/complete",
            headers={**headers, "If-Match": f'"{current["version"]}"'},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        blocked = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"checked": True},
            headers={
                **headers,
                "If-Match": f'"{assigned.json()["version"]}"',
                "Idempotency-Key": "contract-grocery-completed-edit",
            },
        )
        assert blocked.status_code == 409

        reopened = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list/reopen",
            headers={**headers, "If-Match": f'"{completed.json()["version"]}"'},
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "current"
        assert seeded["entry"]["id"]
