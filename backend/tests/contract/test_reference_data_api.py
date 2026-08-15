from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.cli import reference_data
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.jobs import ProcessingJob


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
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def test_reference_data_status_and_install_surface(
    isolated_database_url: str, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        status = client.get("/api/v1/reference-data/status", headers=headers)
        assert status.status_code == 200
        body = status.json()
        assert body["available"] is False
        assert set(body["missing"]) == {"foundation", "sr_legacy"}
        assert body["releases"] == []
        assert body["job"] is None

        accepted = client.post(
            "/api/v1/reference-data/install",
            headers={**headers, "Idempotency-Key": "install-replay-key-0001"},
            json={"datasets": ["foundation_sr_legacy"]},
        )
        assert accepted.status_code == 202
        job_id = accepted.json()["jobId"]

        replay = client.post(
            "/api/v1/reference-data/install",
            headers={**headers, "Idempotency-Key": "install-replay-key-0001"},
            json={"datasets": ["foundation_sr_legacy"]},
        )
        assert replay.status_code == 202
        assert replay.json()["jobId"] == job_id

        with client.app.state.sessions() as session:
            job = session.get(ProcessingJob, job_id)
            assert job is not None
            assert job.kind == "reference_data_install"
            assert job.status == "queued"

        running = client.get("/api/v1/reference-data/status", headers=headers)
        assert running.json()["job"]["status"] == "queued"


def test_reference_data_install_rejects_duplicate_in_flight(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        first = client.post(
            "/api/v1/reference-data/install",
            headers={**headers, "Idempotency-Key": "install-first-key-0001"},
            json={"datasets": ["foundation_sr_legacy"]},
        )
        assert first.status_code == 202
        second = client.post(
            "/api/v1/reference-data/install",
            headers={**headers, "Idempotency-Key": "install-second-key-0001"},
            json={"datasets": ["branded"]},
        )
        assert second.status_code == 409
        assert second.json()["code"] == "install_in_flight"
