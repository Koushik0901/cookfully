from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings


def test_export_job_status_and_one_time_download(
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
        headers = {
            "X-CSRF-Token": client.cookies["cookfully_csrf"],
            "Idempotency-Key": "portable-export-0001",
        }
        accepted = client.post("/api/v1/exports", json={"includeMedia": True}, headers=headers)
        assert accepted.status_code == 202
        assert accepted.elapsed.total_seconds() < 5
        assert accepted.json()["status"] == "queued"
        replay = client.post("/api/v1/exports", json={"includeMedia": True}, headers=headers)
        assert replay.status_code == 202 and replay.json() == accepted.json()
        job_id = UUID(accepted.json()["jobId"])
        app.state.exports.run(job_id)
        progress = client.get(f"/api/v1/jobs/{job_id}")
        assert progress.status_code == 200 and progress.json()["status"] == "succeeded"
        download = client.get(f"/api/v1/exports/{job_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/zip"
        assert download.content.startswith(b"PK")
        repeated = client.get(f"/api/v1/exports/{job_id}/download")
        assert repeated.status_code == 410
