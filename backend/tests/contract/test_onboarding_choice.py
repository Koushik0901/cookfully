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


def test_onboarding_persists_reference_data_choice(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        onboarding = client.get("/api/v1/owner/onboarding", headers=headers)
        assert onboarding.status_code == 200
        version = onboarding.json()["version"]

        resolved = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={
                "state": "completed",
                "referenceDataChoice": "foundation_sr_legacy",
                "version": version,
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["referenceDataChoice"] == "foundation_sr_legacy"

        reloaded = client.get("/api/v1/owner/onboarding", headers=headers)
        assert reloaded.json()["referenceDataChoice"] == "foundation_sr_legacy"
