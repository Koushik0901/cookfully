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
        "decisionAssistToleranceDv": "0.02",
        "monthlyCapUsd": "2.00",
        "version": version,
        **overrides,
    }


def test_requires_an_owner_session(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        assert client.get("/api/v1/openrouter/settings").status_code in {401, 403}


def _feature(body: dict[str, object], purpose: str) -> dict[str, object]:
    features = body["decisionFeatures"]
    assert isinstance(features, list)
    return next(item for item in features if item["purpose"] == purpose)


def test_defaults_have_every_feature_on_and_no_key(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        body = client.get("/api/v1/openrouter/settings").json()
        assert body["keyConfigured"] is False
        assert body["keyHint"] is None
        assert body["decisionAssistToleranceDv"] == "0.02"
        assert body["monthlyCapUsd"] == "2"
        assert body["spentThisMonthUsd"] == "0"
        assert {item["purpose"] for item in body["decisionFeatures"]} >= {
            "match_referee",
            "recipe_facets",
        }
        assert all(item["enabled"] for item in body["decisionFeatures"])
        assert _feature(body, "match_referee")["models"] == [
            "typesafe/jev-1.14",
            "cloudflare/clef",
        ]


def test_feature_edits_persist_and_untouched_features_keep_defaults(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        version = client.get("/api/v1/openrouter/settings").json()["version"]
        saved = client.put(
            "/api/v1/openrouter/settings",
            json=_write(
                version,
                monthlyCapUsd="5.50",
                decisionFeatures=[
                    {"purpose": "shelf_life", "enabled": False, "models": []},
                    {"purpose": "match_referee", "enabled": True, "models": ["typesafe/jev-1.14"]},
                ],
            ),
            headers=headers,
        )
        assert saved.status_code == 200, saved.text
        body = client.get("/api/v1/openrouter/settings").json()
        assert body["monthlyCapUsd"] == "5.5"
        assert _feature(body, "shelf_life") == {
            "purpose": "shelf_life",
            "enabled": False,
            "models": [],
        }
        assert _feature(body, "match_referee")["models"] == ["typesafe/jev-1.14"]
        assert _feature(body, "recipe_facets")["enabled"] is True

        # A later save that omits features leaves them as they were.
        client.put("/api/v1/openrouter/settings", json=_write(version + 1), headers=headers)
        again = client.get("/api/v1/openrouter/settings").json()
        assert _feature(again, "shelf_life")["enabled"] is False


def test_spend_this_month_comes_from_the_decision_ledger(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        engine = create_engine(isolated_database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO decision_answers (id, purpose, model, request_hash, answers, "
                    "cost_usd) VALUES (gen_random_uuid(), 'p', 'm', 'h', '{}', 0.000123)"
                )
            )
        engine.dispose()
        body = client.get("/api/v1/openrouter/settings").json()
        assert body["spentThisMonthUsd"] == "0.000123"


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
            json=_write(
                version + 1,
                decisionFeatures=[{"purpose": "match_referee", "enabled": False, "models": []}],
            ),
            headers=headers,
        )
        assert kept.json()["keyConfigured"] is True
        assert _feature(kept.json(), "match_referee")["enabled"] is False

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
            _write(version, monthlyCapUsd="-1"),
            _write(version, monthlyCapUsd="101"),
            _write(
                version,
                decisionFeatures=[{"purpose": "match_referee", "enabled": True, "models": []}],
            ),
            _write(
                version,
                decisionFeatures=[
                    {"purpose": "match_referee", "enabled": True, "models": ["bad model!"]}
                ],
            ),
            _write(
                version,
                decisionFeatures=[{"purpose": "nope", "enabled": True, "models": ["a/b"]}],
            ),
            _write(
                version,
                decisionFeatures=[
                    {"purpose": "match_referee", "enabled": True, "models": ["a/b", "a/b"]}
                ],
            ),
            _write(
                version,
                decisionFeatures=[
                    {
                        "purpose": "match_referee",
                        "enabled": True,
                        "models": ["a/b", "c/d", "e/f", "g/h"],
                    }
                ],
            ),
            _write(
                version,
                decisionFeatures=[
                    {"purpose": "shelf_life", "enabled": False, "models": []},
                    {"purpose": "shelf_life", "enabled": True, "models": ["a/b"]},
                ],
            ),
            _write(version, unknownField=1),
            _write(2**40),
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
