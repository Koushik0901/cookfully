"""Settings API under hostile input: the key never leaks, and nothing invalid is stored."""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_openrouter_settings_api import KEY, _write, authenticate, client_for

SECRET = "sk-or-v1-ULTRA-secret-9999"


def _put(client: Any, headers: dict[str, str], body: dict[str, object]) -> Any:
    return client.put("/api/v1/openrouter/settings", json=body, headers=headers)


def _version(client: Any) -> int:
    return client.get("/api/v1/openrouter/settings").json()["version"]


@pytest.mark.parametrize(
    "bad_key",
    [
        "short",
        "x" * 7,
        "x" * 257,
        "sk-or key with spaces 12345",
        "sk-or-v1-éééééé",
        "sk-or-v1-abcdef\x00ghij",
        "sk-or-v1-abcdef\x1bghij",
        "sk-or-v1-abcdef\x7fghij",
        "sk-or-v1-abc\ndef12345",
        "‮sk-or-v1-abcdefghij",
    ],
)
def test_a_malformed_key_is_rejected_stored_nowhere_and_not_echoed(
    isolated_database_url: str, tmp_path: Path, bad_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        with caplog.at_level(logging.DEBUG):
            response = _put(client, headers, _write(_version(client), apiKey=bad_key))
        assert response.status_code == 422
        assert bad_key not in response.text, "a rejected key must not be echoed in the error"
        assert bad_key not in caplog.text
        assert client.get("/api/v1/openrouter/settings").json()["keyConfigured"] is False


def test_a_valid_key_never_appears_in_any_response_log_or_error(
    isolated_database_url: str, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        with caplog.at_level(logging.DEBUG):
            saved = _put(client, headers, _write(_version(client), apiKey=SECRET))
            fetched = client.get("/api/v1/openrouter/settings")
            # A later, invalid write that happens to carry the key again.
            invalid = {**_write(0, monthlyCapUsd="-1"), "apiKey": SECRET}
            bad = _put(client, headers, invalid)
            stale = _put(client, headers, _write(1, apiKey=SECRET))
        for response in (saved, fetched, bad, stale):
            assert SECRET not in response.text
            assert SECRET not in str(response.headers)
        assert SECRET not in caplog.text
        assert fetched.json()["keyHint"] == "9999"


@pytest.mark.parametrize(
    "models",
    [
        ["a/b", "a/b"],
        ["a/b", "c/d", "e/f", "g/h"],
        ["../../etc/passwd"],
        ["model with spaces"],
        ["x" * 121],
        ["a/b\n"],
        ["a/b;rm -rf /"],
        ["‮a/b"],
        [""],
        [None],
        [7],
    ],
)
def test_hostile_model_lists_are_rejected_and_nothing_is_stored(
    isolated_database_url: str, tmp_path: Path, models: list[object]
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        version = _version(client)
        body = _write(
            version,
            decisionFeatures=[{"purpose": "grocery_tidy", "enabled": True, "models": models}],
        )
        response = _put(client, headers, body)
        assert response.status_code == 422, response.text
        assert _version(client) == version


@pytest.mark.parametrize(
    "feature",
    [
        {"purpose": "not_a_purpose", "enabled": True, "models": ["a/b"]},
        {"purpose": "grocery_tidy", "enabled": "yes please", "models": ["a/b"]},
        {"purpose": "grocery_tidy", "models": ["a/b"]},
        {"purpose": "grocery_tidy", "enabled": True, "models": ["a/b"], "extra": 1},
        {"purpose": ["grocery_tidy"], "enabled": True, "models": ["a/b"]},
        "grocery_tidy",
        None,
    ],
)
def test_malformed_feature_entries_are_rejected(
    isolated_database_url: str, tmp_path: Path, feature: object
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        response = _put(client, headers, _write(_version(client), decisionFeatures=[feature]))
        assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("monthlyCapUsd", "-0.01"),
        ("monthlyCapUsd", "100.01"),
        ("monthlyCapUsd", "NaN"),
        ("monthlyCapUsd", "Infinity"),
        ("monthlyCapUsd", "1e999"),
        ("monthlyCapUsd", ""),
        ("monthlyCapUsd", None),
        ("monthlyCapUsd", [1]),
        ("monthlyCapUsd", True),
        ("decisionAssistToleranceDv", "0"),
        ("decisionAssistToleranceDv", "-0.01"),
        ("decisionAssistToleranceDv", "0.1001"),
        ("decisionAssistToleranceDv", "NaN"),
        ("decisionAssistToleranceDv", "1"),
        ("decisionAssistToleranceDv", None),
        ("version", 0),
        ("version", -1),
        ("version", "1; DROP TABLE x"),
        ("version", 1.5),
        ("version", 10**30),
        ("version", None),
        ("cleanupModel", "bad model"),
        ("cleanupModel", "x" * 500),
        ("cleanupModel", None),
    ],
)
def test_out_of_range_numbers_and_types_are_rejected(
    isolated_database_url: str, tmp_path: Path, field: str, value: object
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        body = _write(_version(client))
        body[field] = value
        assert _put(client, headers, body).status_code == 422


@pytest.mark.parametrize("cap", ["0", "0.00", "100", "100.000000", "0.000001"])
def test_boundary_caps_are_accepted(isolated_database_url: str, tmp_path: Path, cap: str) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        assert _put(client, headers, _write(_version(client), monthlyCapUsd=cap)).status_code == 200


def test_two_racing_writers_cannot_both_win(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        version = _version(client)
        first = _put(client, headers, _write(version, monthlyCapUsd="3.00"))
        second = _put(client, headers, _write(version, monthlyCapUsd="9.00"))
        assert first.status_code == 200
        assert second.status_code == 409
        assert Decimal(client.get("/api/v1/openrouter/settings").json()["monthlyCapUsd"]) == 3


def test_sending_a_key_and_asking_to_remove_it_is_rejected_and_changes_nothing(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        _put(client, headers, _write(_version(client), apiKey=KEY))
        before = client.get("/api/v1/openrouter/settings").json()
        response = _put(client, headers, _write(before["version"], apiKey=SECRET, clearApiKey=True))
        assert response.status_code == 422
        assert SECRET not in response.text
        assert client.get("/api/v1/openrouter/settings").json() == before


def test_the_settings_routes_refuse_anonymous_and_cross_site_writes(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        no_csrf = client.put("/api/v1/openrouter/settings", json=_write(1, apiKey=SECRET))
        assert no_csrf.status_code in (401, 403)
        assert SECRET not in no_csrf.text
    with client_for(isolated_database_url, tmp_path) as anonymous:
        assert anonymous.get("/api/v1/openrouter/settings").status_code in (401, 403)
        assert anonymous.put("/api/v1/openrouter/settings", json=_write(1)).status_code in (
            401,
            403,
        )


def test_the_same_feature_twice_or_a_flood_of_features_is_rejected(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        one = {"purpose": "grocery_tidy", "enabled": True, "models": ["a/b"]}
        twice = _put(client, headers, _write(_version(client), decisionFeatures=[one, one]))
        flood = _put(client, headers, _write(_version(client), decisionFeatures=[one] * 50))
        assert twice.status_code == flood.status_code == 422


def test_extra_unknown_fields_are_rejected(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        body = _write(_version(client), isAdmin=True, apiKeyPlain="x")
        assert _put(client, headers, body).status_code == 422
