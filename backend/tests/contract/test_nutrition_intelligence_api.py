from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

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


def test_settings_estimate_and_update_require_reviewed_estimate(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        current = client.get("/api/v1/nutrition-intelligence/settings", headers=headers)
        assert current.status_code == 200
        assert current.json()["backend"] == "hashing"

        estimate = client.post(
            "/api/v1/nutrition-intelligence/estimate",
            headers=headers,
            json={"backend": "hashing", "modelName": "BAAI/bge-small-en-v1.5", "concurrency": 2},
        )
        assert estimate.status_code == 200
        estimate_body = estimate.json()
        assert estimate_body["status"] == "safe"
        assert estimate_body["downloadBytes"] == 0

        updated = client.put(
            "/api/v1/nutrition-intelligence/settings",
            headers=headers,
            json={
                "backend": "hashing",
                "modelName": "BAAI/bge-small-en-v1.5",
                "concurrency": 2,
                "version": current.json()["version"],
                "estimateHash": estimate_body["estimateHash"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["concurrency"] == 2

        stale = client.put(
            "/api/v1/nutrition-intelligence/settings",
            headers=headers,
            json={
                "backend": "hashing",
                "modelName": "BAAI/bge-small-en-v1.5",
                "concurrency": 1,
                "version": current.json()["version"],
                "estimateHash": estimate_body["estimateHash"],
            },
        )
        assert stale.status_code == 409
