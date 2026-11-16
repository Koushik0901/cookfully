from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings

KEY = "sk-or-v1-super-secret-1234"


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
    return {"X-CSRF-Token": client.cookies.get("cookfully_csrf") or ""}


def _write(version: int, **overrides: object) -> dict[str, object]:
    return {
        "cleanupModel": "",
        "decisionAssistEnabled": True,
        "decisionAssistModel": "typesafe/jev-1.14",
        "decisionAssistToleranceDv": "0.02",
        "version": version,
        **overrides,
    }


def test_requires_an_owner_session(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        assert client.get("/api/v1/openrouter/settings").status_code in {401, 403}


def test_defaults_have_assist_on_and_no_key(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        body = client.get("/api/v1/openrouter/settings").json()
        assert body["keyConfigured"] is False
        assert body["keyHint"] is None
        assert body["decisionAssistEnabled"] is True
        assert body["decisionAssistModel"] == "typesafe/jev-1.14"
        assert body["decisionAssistToleranceDv"] == "0.02"


def test_key_is_encrypted_at_rest_and_never_returned(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        version = client.get("/api/v1/openrouter/settings").json()["version"]
        saved = client.put(
            "/api/v1/openrouter/settings",
            json=_write(version, apiKey=KEY, cleanupModel="openai/some-model"),
            headers=headers,
        )
        assert saved.status_code == 200, saved.text
        assert KEY not in saved.text
        assert saved.json()["keyConfigured"] is True
        assert saved.json()["keyHint"] == "1234"
        assert KEY not in client.get("/api/v1/openrouter/settings").text

        engine = create_engine(isolated_database_url)
        with engine.connect() as connection:
            stored = connection.execute(
                text("SELECT api_key_encrypted FROM openrouter_settings")
            ).scalar_one()
        engine.dispose()
        assert stored and KEY not in stored

        import_settings = client.get("/api/v1/recipe-import/settings").json()
        assert import_settings["openrouterConfigured"] is True
        assert import_settings["openrouterModel"] == "openai/some-model"


def test_omitting_the_key_keeps_it_and_clear_removes_it(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        version = client.get("/api/v1/openrouter/settings").json()["version"]
        client.put("/api/v1/openrouter/settings", json=_write(version, apiKey=KEY), headers=headers)

        kept = client.put(
            "/api/v1/openrouter/settings",
            json=_write(version + 1, decisionAssistEnabled=False),
            headers=headers,
        )
        assert kept.json()["keyConfigured"] is True
        assert kept.json()["decisionAssistEnabled"] is False

        cleared = client.put(
            "/api/v1/openrouter/settings",
            json=_write(version + 2, clearApiKey=True),
            headers=headers,
        )
        assert cleared.json()["keyConfigured"] is False
        assert cleared.json()["keyHint"] is None


def test_rejects_stale_versions_and_invalid_input(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        version = client.get("/api/v1/openrouter/settings").json()["version"]

        stale = client.put("/api/v1/openrouter/settings", json=_write(99), headers=headers)
        assert stale.status_code == 409
        assert stale.json()["code"] == "openrouter_settings_stale"

        for bad in (
            _write(version, apiKey="short"),
            _write(version, apiKey="has space in it"),
            _write(version, decisionAssistToleranceDv="0"),
            _write(version, decisionAssistToleranceDv="0.5"),
            _write(version, decisionAssistModel="bad model!"),
            _write(version, unknownField=1),
        ):
            response = client.put("/api/v1/openrouter/settings", json=bad, headers=headers)
            assert response.status_code == 422, bad


def test_a_key_encrypted_under_another_secret_is_treated_as_absent(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        version = client.get("/api/v1/openrouter/settings").json()["version"]
        client.put("/api/v1/openrouter/settings", json=_write(version, apiKey=KEY), headers=headers)
        engine = create_engine(isolated_database_url)
        with engine.begin() as connection:
            connection.execute(text("UPDATE openrouter_settings SET api_key_encrypted = 'garbage'"))
        engine.dispose()
        assert client.get("/api/v1/openrouter/settings").json()["keyConfigured"] is False
