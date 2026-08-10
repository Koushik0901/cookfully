from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from vigor_vine.api.main import create_app
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.config import Settings
from vigor_vine.infrastructure.models.identity import AccessToken, OwnerAccount
from vigor_vine.mcp.security import RATE_LIMITS
from vigor_vine.mcp.write_tools import WriteTools


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
    isolated_database_url: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
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


def mcp_call(
    client: TestClient, secret: str, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    response = client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {secret}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200
    return response.json()["result"]


def test_mcp_stale_version_aborts_idempotency_and_rate_limit_revocation_fail_closed(
    isolated_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        goal = {
            "mode": "maintain",
            "maintenanceKcal": "2200",
            "caloriesKcal": "2200",
            "proteinG": "180",
            "carbohydrateG": "220",
            "fatG": "65",
            "effectiveFrom": "2026-03-01",
            "effectiveTo": None,
            "mealTargets": [],
        }
        assert client.put("/api/v1/goals/current", json=goal, headers=headers).status_code == 200
        recipe = client.post(
            "/api/v1/recipes",
            headers=headers,
            json={
                "title": "Security bowl",
                "yieldQuantity": "2",
                "yieldUnit": "servings",
                "ingredients": [{"originalText": "tofu"}],
                "instructions": [],
            },
        ).json()
        for index, field in enumerate(("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")):
            assert (
                client.post(
                    f"/api/v1/recipes/{recipe['id']}/nutrition/corrections",
                    headers={**headers, "Idempotency-Key": f"mcp-security-correction-{index}"},
                    json={"field": field, "decimalValue": "10"},
                ).status_code
                == 201
            )
        entry = client.post(
            "/api/v1/meal-plans/2026-03-09/entries",
            headers={**headers, "Idempotency-Key": "mcp-security-plan-entry"},
            json={
                "localDate": "2026-03-09",
                "mealSlot": "lunch",
                "recipeId": recipe["id"],
                "servings": "1",
            },
        ).json()
        with client.app.state.sessions() as session:
            owner = session.scalar(select(OwnerAccount.id).limit(1))
        assert owner is not None
        tools = WriteTools(
            client.app.state.meal_plans,
            client.app.state.grocery_lists,
            client.app.state.idempotency,
        )
        with pytest.raises(DomainError) as stale:
            tools.update_meal_plan_entry(
                owner,
                entry_id=entry["id"],
                local_date="2026-03-10",
                meal_slot="dinner",
                servings="1",
                expected_version=999,
                idempotency_key="mcp-security-stale-01",
            )
        assert getattr(stale.value, "code", None) == "stale_version"
        recovered = tools.update_meal_plan_entry(
            owner,
            entry_id=entry["id"],
            local_date="2026-03-10",
            meal_slot="dinner",
            servings="1",
            expected_version=entry["version"],
            idempotency_key="mcp-security-stale-01",
        )
        assert recovered["entry"]["localDate"] == "2026-03-10"

        token = client.post(
            "/api/v1/access-tokens",
            headers=headers,
            json={"name": "Rate limited", "scopes": ["plans:read"]},
        ).json()
        monkeypatch.setitem(RATE_LIMITS, "read", 0)
        limited = mcp_call(
            client,
            token["secret"],
            "get_meal_plan",
            {"week_start": "2026-03-09"},
        )
        assert limited["isError"] is True
        assert limited["structuredContent"]["error"]["code"] == "rate_limit_exceeded"
        assert "rate_limit_exceeded" in str(limited)
        assert token["secret"] not in str(limited)

        assert (
            client.delete(
                f"/api/v1/access-tokens/{token['id']}",
                headers={**headers, "Idempotency-Key": "mcp-security-revoke-token"},
            ).status_code
            == 204
        )
        revoked = client.post(
            "/mcp",
            headers={
                "Authorization": f"Bearer {token['secret']}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert revoked.status_code == 401
        assert revoked.json()["code"] == "token_invalid"
