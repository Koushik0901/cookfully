from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vigor_vine.api.main import create_app
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.config import Settings


def test_csrf_token_scope_and_browser_only_token_management(
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
        login = client.post(
            "/api/v1/auth/session",
            json={"email": "owner@example.com", "password": "correct horse battery staple"},
        )
        assert login.status_code == 204
        csrf = client.cookies["vv_csrf"]

        rejected = client.post(
            "/api/v1/recipes",
            json={
                "title": "CSRF must fail",
                "yieldQuantity": "1.000",
                "yieldUnit": "servings",
                "ingredients": [{"originalText": "100 g oats"}],
                "instructions": ["Mix."],
            },
        )
        assert rejected.status_code == 403
        assert rejected.json()["code"] == "csrf_invalid"

        created = client.post(
            "/api/v1/access-tokens",
            headers={"X-CSRF-Token": csrf},
            json={"name": "Recipe reader", "scopes": ["recipes:read"], "expiresAt": None},
        )
        assert created.status_code == 201
        secret = created.json()["secret"]
        bearer = {"Authorization": f"Bearer {secret}"}

        assert client.get("/api/v1/recipes", headers=bearer).status_code == 200
        scope_denied = client.post(
            "/api/v1/recipes",
            headers=bearer,
            json={
                "title": "Scope must fail",
                "yieldQuantity": "1.000",
                "yieldUnit": "servings",
                "ingredients": [{"originalText": "100 g oats"}],
                "instructions": ["Mix."],
            },
        )
        assert scope_denied.status_code == 403
        assert scope_denied.json()["code"] == "browser_session_required"

        with pytest.raises(DomainError) as missing_scope:
            app.state.access_tokens.authenticate(secret, {"plans:write"})
        assert missing_scope.value.code == "insufficient_scope"

        browser_only = client.get("/api/v1/access-tokens", headers=bearer)
        assert browser_only.status_code == 403
        assert browser_only.json()["code"] == "browser_session_required"
        assert secret not in scope_denied.text
        assert secret not in browser_only.text
