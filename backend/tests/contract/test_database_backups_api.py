from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings


def _write_backup(root: Path) -> None:
    database_root = root / "database"
    database_root.mkdir(parents=True)
    dump = database_root / "cookfully-postgres-20260827T090000Z.dump"
    dump.write_bytes(b"database backup")
    checksum = hashlib.sha256(dump.read_bytes()).hexdigest()
    (database_root / f"{dump.name}.sha256").write_text(
        f"{checksum}  {dump.name}\n", encoding="utf-8"
    )
    (database_root / "cookfully-postgres-20260827T090000Z.json").write_text(
        json.dumps(
            {
                "bytes": dump.stat().st_size,
                "createdAt": "2026-08-27T09:00:00Z",
                "filename": dump.name,
                "reason": "schedule",
                "sha256": checksum,
            }
        ),
        encoding="utf-8",
    )


def test_database_backup_status_is_owner_only_and_manual_requests_are_queued(
    isolated_database_url: str, tmp_path: Path
) -> None:
    backup_root = tmp_path / "backups"
    _write_backup(backup_root)
    app = create_app(
        Settings(
            environment="test",
            database_url=isolated_database_url,
            owner_email="owner@example.com",
            owner_bootstrap_password="correct horse battery staple",
            media_root=tmp_path / "media",
            export_root=tmp_path / "exports",
            erasure_ledger_root=tmp_path / "ledger",
            backup_root=backup_root,
        )
    )
    with TestClient(app) as client:
        unauthorized = client.get("/api/v1/database-backups")
        assert unauthorized.status_code == 401

        login = client.post(
            "/api/v1/auth/session",
            json={"email": "owner@example.com", "password": "correct horse battery staple"},
        )
        assert login.status_code == 204
        status_response = client.get("/api/v1/database-backups")
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["storageMode"] == "host_bind_mount"
        assert status_body["schedule"] == "02:00"
        assert status_body["retentionCount"] == 14
        assert status_body["latest"]["reason"] == "schedule"
        assert status_body["pendingManualRequest"] is False

        requested = client.post(
            "/api/v1/database-backups/request",
            headers={"X-CSRF-Token": client.cookies["cookfully_csrf"]},
        )
        assert requested.status_code == 202
        assert requested.json()["status"] == "queued"
        assert len(requested.json()["requestId"]) == 32

        after_request = client.get("/api/v1/database-backups")
        assert after_request.json()["pendingManualRequest"] is True
