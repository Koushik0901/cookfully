"""Requests found by Schemathesis that used to crash the API with a 500.

Each must now be rejected with a client error, never a server error. See docs/ci.md.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.domain.common import MAX_VERSION
from cookfully.infrastructure.config import Settings


def _client(isolated_database_url: str, tmp_path: Path) -> TestClient:
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


def _sign_in(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def _preferences(timezone: str) -> dict[str, object]:
    return {
        "displayName": "Owner",
        "timezone": timezone,
        "weekStartsOn": 1,
        "healthProfile": {"dietaryPattern": "no_preference", "avoidIngredients": []},
        "version": 1,
    }


@pytest.mark.parametrize("timezone", ["", "../etc/passwd", "Not/AZone", "/UTC"])
def test_malformed_timezones_are_rejected_not_crashed(
    isolated_database_url: str, tmp_path: Path, timezone: str
) -> None:
    """``ZoneInfo("")`` raises ValueError rather than ZoneInfoNotFoundError."""

    with _client(isolated_database_url, tmp_path) as client:
        headers = _sign_in(client)
        response = client.put(
            "/api/v1/owner/preferences", json=_preferences(timezone), headers=headers
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "invalid_timezone"


def test_versions_beyond_the_database_integer_range_are_rejected_not_crashed(
    isolated_database_url: str, tmp_path: Path
) -> None:
    """A version no row can have used to overflow PostgreSQL's integer and return a 500."""

    with _client(isolated_database_url, tmp_path) as client:
        headers = _sign_in(client)
        response = client.delete(
            f"/api/v1/foods/user/{uuid4()}",
            params={"expectedVersion": MAX_VERSION + 1},
            headers=headers,
        )

        assert response.status_code == 422, response.text


def test_the_largest_valid_version_is_still_a_normal_conflict_or_not_found(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with _client(isolated_database_url, tmp_path) as client:
        headers = _sign_in(client)
        response = client.delete(
            f"/api/v1/foods/user/{uuid4()}",
            params={"expectedVersion": MAX_VERSION},
            headers=headers,
        )

        assert response.status_code in {404, 409}, response.text


def test_text_the_database_cannot_store_is_a_client_error(
    isolated_database_url: str, tmp_path: Path
) -> None:
    """A NUL byte in a query string reached PostgreSQL and produced a 500."""

    with _client(isolated_database_url, tmp_path) as client:
        _sign_in(client)
        response = client.get(
            "/api/v1/jobs/current", params={"aggregateId": str(uuid4()), "aggregateType": "a\x00b"}
        )

        assert response.status_code == 422, response.text
        assert response.json()["code"] == "invalid_value"


@pytest.mark.parametrize("timezone", ["", "../etc/passwd", "Not/AZone"])
def test_today_in_timezone_rejects_malformed_names_with_a_value_error(timezone: str) -> None:
    from cookfully.domain.common import today_in_timezone

    with pytest.raises(ValueError, match="invalid timezone"):
        today_in_timezone(timezone)


def _food(**overrides: object) -> dict[str, object]:
    return {
        "displayName": "House oats",
        "caloriesKcal": "380",
        "proteinG": "13",
        "carbohydrateG": "67",
        "fatG": "7",
        **overrides,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"carbohydrateG": "1" + "0" * 30},
        {"caloriesKcal": "100000001"},
        {"proteinG": "1E+40"},
        {"fatG": "99999999999999999999.5"},
        {"basisGrams": "1" + "0" * 25},
        {"typicalServingG": "1" + "0" * 25},
        {"typicalServingG": "0"},
        {"typicalServingG": "-5"},
        {"brand": "b" * 241},
        {"typicalServingUnit": "u" * 21},
    ],
)
def test_owner_foods_outside_the_storable_range_are_rejected_not_crashed(
    isolated_database_url: str, tmp_path: Path, overrides: dict[str, object]
) -> None:
    """Amounts beyond NUMERIC(20, 6) (and over-long text) used to raise inside quantize/INSERT."""

    with _client(isolated_database_url, tmp_path) as client:
        headers = _sign_in(client)
        created = client.post("/api/v1/foods/user", json=_food(), headers=headers)
        assert created.status_code == 201, created.text
        food_id = created.json()["id"]

        rejected_create = client.post(
            "/api/v1/foods/user", json=_food(**overrides), headers=headers
        )
        rejected_update = client.put(
            f"/api/v1/foods/user/{food_id}",
            json={**_food(**overrides), "expectedVersion": 1},
            headers=headers,
        )

        assert rejected_create.status_code == 422, rejected_create.text
        assert rejected_update.status_code == 422, rejected_update.text


def test_owner_foods_at_the_range_limits_are_still_accepted(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with _client(isolated_database_url, tmp_path) as client:
        headers = _sign_in(client)
        response = client.post(
            "/api/v1/foods/user",
            json=_food(
                caloriesKcal="100000000",
                basisGrams="100000000",
                typicalServingG="100000000",
                brand="b" * 240,
                typicalServingUnit="u" * 20,
            ),
            headers=headers,
        )
        assert response.status_code == 201, response.text
