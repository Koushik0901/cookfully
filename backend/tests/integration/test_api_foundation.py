from fastapi.testclient import TestClient

from vigor_vine.api.main import create_app
from vigor_vine.infrastructure.config import Settings


def test_health_login_csrf_preferences_and_problem_contract(isolated_database_url: str) -> None:
    settings = Settings(
        database_url=isolated_database_url,
        owner_bootstrap_password="correct horse battery staple",
    )
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        login = client.post(
            "/api/v1/auth/session",
            json={
                "email": str(settings.owner_email),
                "password": "correct horse battery staple",
            },
        )
        assert login.status_code == 204
        assert login.cookies.get("vv_session")
        assert "HttpOnly" in login.headers["set-cookie"]

        rejected = client.put(
            "/api/v1/owner/preferences",
            json={"timezone": "America/Vancouver", "weekStartsOn": 1, "version": 1},
        )
        assert rejected.status_code == 403
        assert rejected.headers["content-type"].startswith("application/problem+json")
        assert rejected.json()["code"] == "csrf_invalid"

        accepted = client.put(
            "/api/v1/owner/preferences",
            headers={"x-csrf-token": login.cookies["vv_csrf"]},
            json={"timezone": "America/Vancouver", "weekStartsOn": 7, "version": 1},
        )
        assert accepted.status_code == 200
        assert accepted.json() == {
            "timezone": "America/Vancouver",
            "weekStartsOn": 7,
            "version": 2,
        }
