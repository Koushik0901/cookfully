from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings

PASSWORD = "correct horse battery staple"


def _settings(url: str, tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        environment="test",
        database_url=url,
        owner_email="owner@example.com",
        owner_bootstrap_password=PASSWORD,
        media_root=tmp_path / "media",
        erasure_ledger_root=tmp_path / "ledger",
        **overrides,  # type: ignore[arg-type]
    )


def _login(client: TestClient, password: str) -> int:
    return client.post(
        "/api/v1/auth/session", json={"email": "owner@example.com", "password": password}
    ).status_code


def test_responses_carry_defensive_headers(isolated_database_url: str, tmp_path: Path) -> None:
    with TestClient(create_app(_settings(isolated_database_url, tmp_path))) as client:
        headers = client.get("/api/v1/health").headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
        assert headers["cache-control"] == "no-store"
        assert "strict-transport-security" not in headers

    with TestClient(
        create_app(_settings(isolated_database_url, tmp_path)), base_url="https://testserver"
    ) as secure:
        assert "max-age" in secure.get("/api/v1/health").headers["strict-transport-security"]


def test_repeated_wrong_passwords_lock_sign_in_even_for_the_right_one(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with TestClient(create_app(_settings(isolated_database_url, tmp_path))) as client:
        for _ in range(5):
            assert _login(client, "definitely the wrong password") == 401
        locked = client.post(
            "/api/v1/auth/session", json={"email": "owner@example.com", "password": PASSWORD}
        )
        assert locked.status_code == 429
        assert locked.json()["code"] == "login_throttled"


def test_a_successful_sign_in_clears_earlier_failures(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with TestClient(create_app(_settings(isolated_database_url, tmp_path))) as client:
        for _ in range(4):
            assert _login(client, "definitely the wrong password") == 401
        assert _login(client, PASSWORD) == 204
        for _ in range(4):
            assert _login(client, "definitely the wrong password") == 401
        assert _login(client, PASSWORD) == 204


def test_production_serves_no_api_docs_or_schema(tmp_path: Path) -> None:
    settings = Settings(
        environment="production",
        secret_key="x" * 40,  # type: ignore[arg-type]
        owner_bootstrap_password="a-real-production-password",  # type: ignore[arg-type]
        instance_id="018f3b0a-0000-7000-8000-0000000000aa",  # type: ignore[arg-type]
        cookie_secure=True,
        public_base_url="https://cookfully.tailnet.ts.net",  # type: ignore[arg-type]
        api_base_url="https://cookfully.tailnet.ts.net",  # type: ignore[arg-type]
        trusted_proxy_cidrs=("172.31.250.0/24",),
        media_root=tmp_path / "media",
        erasure_ledger_root=tmp_path / "ledger",
    )
    client = TestClient(create_app(settings))
    assert client.get("/api/openapi.json").status_code == 404
    assert client.get("/api/docs").status_code == 404
