from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings

PASSWORD = "correct horse battery staple"


def client_for(isolated_database_url: str, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=isolated_database_url,
                owner_email="owner@example.com",
                owner_bootstrap_password=PASSWORD,
                media_root=tmp_path / "media",
                erasure_ledger_root=tmp_path / "ledger",
            )
        )
    )


def authenticate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"email": "owner@example.com", "password": PASSWORD},
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def test_login_sets_lax_long_lived_cookies(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        response = client.post(
            "/api/v1/auth/session",
            json={"email": "owner@example.com", "password": PASSWORD},
        )
        assert response.status_code == 204
        set_cookie = response.headers.get_list("set-cookie")
        session_cookie = next(
            value for value in set_cookie if value.startswith("cookfully_session=")
        )
        csrf_cookie = next(value for value in set_cookie if value.startswith("cookfully_csrf="))
        for value in (session_cookie, csrf_cookie):
            lowered = value.lower()
            assert "samesite=lax" in lowered
            assert "expires=" in lowered
        assert "httponly" in session_cookie.lower()
        assert "httponly" not in csrf_cookie.lower()


def test_list_and_revoke_sessions(isolated_database_url: str, tmp_path: Path) -> None:
    with (
        client_for(isolated_database_url, tmp_path) as client,
        client_for(isolated_database_url, tmp_path) as other,
    ):
        authenticate(client)
        authenticate(other)

        listed = client.get("/api/v1/auth/sessions")
        assert listed.status_code == 200
        sessions = listed.json()["sessions"]
        assert len(sessions) == 2
        assert sum(1 for item in sessions if item["isCurrent"]) == 1
        target = next(item for item in sessions if not item["isCurrent"])

        revoked = client.delete(
            f"/api/v1/auth/sessions/{target['id']}",
            headers={"x-csrf-token": client.cookies["cookfully_csrf"]},
        )
        assert revoked.status_code == 204

        assert other.get("/api/v1/auth/sessions").status_code == 401
        remaining = client.get("/api/v1/auth/sessions").json()["sessions"]
        assert len(remaining) == 1
        assert remaining[0]["isCurrent"] is True


def test_revoke_current_session_signs_out(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        listed = client.get("/api/v1/auth/sessions").json()["sessions"]
        current = next(item for item in listed if item["isCurrent"])
        response = client.delete(
            f"/api/v1/auth/sessions/{current['id']}",
            headers={"x-csrf-token": client.cookies["cookfully_csrf"]},
        )
        assert response.status_code == 204
        assert client.get("/api/v1/auth/sessions").status_code == 401


def test_change_password_flow(isolated_database_url: str, tmp_path: Path) -> None:
    with (
        client_for(isolated_database_url, tmp_path) as client,
        client_for(isolated_database_url, tmp_path) as other,
    ):
        authenticate(client)
        authenticate(other)

        response = client.post(
            "/api/v1/auth/password",
            headers={"x-csrf-token": client.cookies["cookfully_csrf"]},
            json={
                "currentPassword": PASSWORD,
                "newPassword": "brand new horse battery staple",
            },
        )
        assert response.status_code == 204

        assert client.get("/api/v1/auth/sessions").status_code == 200
        assert other.get("/api/v1/auth/sessions").status_code == 401

        with client_for(isolated_database_url, tmp_path) as fresh:
            old = fresh.post(
                "/api/v1/auth/session",
                json={"email": "owner@example.com", "password": PASSWORD},
            )
            assert old.status_code == 401
            new = fresh.post(
                "/api/v1/auth/session",
                json={"email": "owner@example.com", "password": "brand new horse battery staple"},
            )
            assert new.status_code == 204


def test_change_password_validation(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        wrong = client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={
                "currentPassword": "wrong current password",
                "newPassword": "brand new horse battery staple",
            },
        )
        assert wrong.status_code == 401
        weak = client.post(
            "/api/v1/auth/password",
            headers=headers,
            json={"currentPassword": PASSWORD, "newPassword": "short"},
        )
        assert weak.status_code == 422


def test_onboarding_is_optional_and_resolves_once(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        pending = client.get("/api/v1/owner/onboarding")
        assert pending.status_code == 200
        assert pending.json() == {
            "state": "pending",
            "firstAction": None,
            "resolvedAt": None,
            "version": 1,
        }

        invalid = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={"state": "pending", "version": 1},
        )
        assert invalid.status_code == 422

        resolved = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={"state": "completed", "firstAction": "manual_recipe", "version": 1},
        )
        assert resolved.status_code == 200
        assert resolved.json()["state"] == "completed"
        assert resolved.json()["firstAction"] == "manual_recipe"
        assert resolved.json()["resolvedAt"] is not None
        assert resolved.json()["version"] == 2

        repeated = client.put(
            "/api/v1/owner/onboarding",
            headers=headers,
            json={"state": "dismissed", "version": 2},
        )
        assert repeated.status_code == 409
