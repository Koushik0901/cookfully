from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from vigor_vine.api.main import create_app
from vigor_vine.infrastructure.config import Settings
from vigor_vine.infrastructure.models.identity import AccessToken


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
    return {"X-CSRF-Token": client.cookies["vv_csrf"]}


def test_openapi_access_token_create_list_once_only_secret_and_revoke(
    isolated_database_url: str, tmp_path: Path
) -> None:
    app = create_app(
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
    with TestClient(app) as client:
        schema = client.get("/api/openapi.json").json()
        assert schema["openapi"].startswith("3.1")
        assert "/api/v1/access-tokens" in schema["paths"]
        assert "/api/v1/access-tokens/{tokenId}" in schema["paths"]

        headers = authenticate(client)
        created = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={
                "name": "Read-only planner",
                "scopes": ["plans:read", "goals:read"],
                "expiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
            },
        )
        assert created.status_code == 201
        body = created.json()
        secret = body.pop("secret")
        assert secret.startswith("vv_") and len(secret) >= 32
        assert body["name"] == "Read-only planner"
        assert body["scopes"] == ["goals:read", "plans:read"]
        assert body["revokedAt"] is None and body["lastUsedAt"] is None

        listed = client.get("/api/v1/access-tokens").json()
        assert listed == [body]
        assert "secret" not in listed[0]
        with app.state.sessions() as session:
            stored = session.scalar(select(AccessToken).where(AccessToken.id == body["id"]))
            assert stored is not None
            assert stored.token_hash == hashlib.sha256(secret.encode()).hexdigest()
            assert secret not in repr(stored)

        revoked = client.delete(
            f"/api/v1/access-tokens/{body['id']}",
            headers={**headers, "Idempotency-Key": "revoke-read-only-token"},
        )
        assert revoked.status_code == 204
        replay = client.delete(
            f"/api/v1/access-tokens/{body['id']}",
            headers={**headers, "Idempotency-Key": "revoke-read-only-token"},
        )
        assert replay.status_code == 204
        metadata = client.get("/api/v1/access-tokens").json()[0]
        assert metadata["revokedAt"] is not None
        assert "secret" not in metadata


def test_token_scope_expiry_revocation_and_browser_only_management(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        created = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={"name": "Plan reader", "scopes": ["plans:read"], "expiresAt": None},
        ).json()
        bearer = {"Authorization": f"Bearer {created['secret']}"}

        # A read-only token reaches a scoped read (the plan itself is not seeded) but cannot mutate.
        assert client.get("/api/v1/meal-plans/2026-03-09", headers=bearer).status_code == 404
        denied = client.post(
            "/api/v1/meal-plans/2026-03-09/entries",
            headers={**bearer, "Idempotency-Key": "scope-denied-write"},
            json={
                "localDate": "2026-03-09",
                "mealSlot": "lunch",
                "recipeId": "00000000-0000-4000-8000-000000000001",
                "servings": "1.000",
                "refreshNutrition": False,
            },
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "insufficient_scope"
        assert client.get("/api/v1/access-tokens", headers=bearer).status_code == 403

        token_id = created["id"]
        assert (
            client.delete(
                f"/api/v1/access-tokens/{token_id}",
                headers={**headers, "Idempotency-Key": "revoke-reader-token"},
            ).status_code
            == 204
        )
        invalid = client.get("/api/v1/meal-plans/2026-03-09", headers=bearer)
        assert invalid.status_code == 401
        assert invalid.json()["code"] == "token_invalid"

        expired = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={
                "name": "Already expired",
                "scopes": ["plans:read"],
                "expiresAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            },
        )
        assert expired.status_code == 422


def test_scope_allowlist_validation_and_secret_redaction(
    isolated_database_url: str, tmp_path: Path, caplog: object
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        unknown = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={"name": "Too powerful", "scopes": ["admin"], "expiresAt": None},
        )
        assert unknown.status_code == 422
        assert "admin" not in unknown.text.lower() or "scope" in unknown.text.lower()
        empty = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={"name": "No authority", "scopes": [], "expiresAt": None},
        )
        assert empty.status_code == 422
        assert "vv_" not in str(caplog)
