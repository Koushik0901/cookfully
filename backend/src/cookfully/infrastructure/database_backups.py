"""Read and request host-owned PostgreSQL backups without exposing host paths."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

MAX_RETENTION_COUNT = 365
MIN_RETENTION_COUNT = 1
SETTINGS_FILENAME = "settings.json"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _as_utc_iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class DatabaseBackupStore:
    """Small filesystem protocol shared by the API and the backup sidecar.

    The sidecar is the only process allowed to create dump files.  The API can
    only enqueue a manual request and read the manifest/status it publishes.
    Keeping that boundary filesystem-only avoids giving the web process direct
    database-dump credentials or a shell escape hatch.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._database_root = self._root / "database"
        self._requests_root = self._root / "requests"
        self._status_path = self._root / "status.json"
        self._settings_path = self._root / SETTINGS_FILENAME

    def request_now(self) -> str:
        self._requests_root.mkdir(parents=True, exist_ok=True)
        request_id = uuid4().hex
        request_path = self._requests_root / f"{request_id}.json"
        payload = {
            "kind": "backup",
            "requestedAt": _as_utc_iso(_utc_now()),
            "requestId": request_id,
        }
        self._write_json(request_path, payload)
        return request_id

    def set_retention_count(self, retention_count: int) -> str:
        """Persist the owner-selected count and ask the sidecar to prune now."""

        if not MIN_RETENTION_COUNT <= retention_count <= MAX_RETENTION_COUNT:
            raise ValueError("retention_count must be between 1 and 365")
        self._write_json(
            self._settings_path,
            {
                "retentionCount": retention_count,
                "updatedAt": _as_utc_iso(_utc_now()),
            },
        )
        return self.request_prune()

    def request_prune(self) -> str:
        """Queue a lightweight prune request without creating a new dump."""

        self._requests_root.mkdir(parents=True, exist_ok=True)
        request_id = uuid4().hex
        request_path = self._requests_root / f"prune-{request_id}.json"
        self._write_json(
            request_path,
            {
                "kind": "prune",
                "requestedAt": _as_utc_iso(_utc_now()),
                "requestId": request_id,
            },
        )
        return request_id

    def status(
        self,
        *,
        schedule: str,
        retention_count: int,
    ) -> dict[str, Any]:
        status = self._read_json(self._status_path)
        effective_retention_count = self.retention_count(retention_count)
        backups = self._backups(limit=effective_retention_count)
        pending = self._pending_requests()
        return {
            "storageMode": "host_bind_mount",
            "schedule": schedule,
            "retentionCount": effective_retention_count,
            "backups": backups,
            "latest": backups[0] if backups else None,
            "lastSuccessAt": status.get("lastSuccessAt"),
            "lastFailure": status.get("lastFailure"),
            "pendingManualRequest": pending,
            "serviceHeartbeatAt": status.get("heartbeatAt"),
        }

    def retention_count(self, default: int) -> int:
        value = self._read_json(self._settings_path).get("retentionCount")
        if type(value) is int and MIN_RETENTION_COUNT <= value <= MAX_RETENTION_COUNT:
            return value
        return default

    def _backups(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not self._database_root.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for manifest_path in self._database_root.glob("*.json"):
            manifest = self._read_json(manifest_path)
            filename = manifest.get("filename")
            if not isinstance(filename, str) or Path(filename).name != filename:
                continue
            dump_path = self._database_root / filename
            if not dump_path.is_file():
                continue
            created_at = manifest.get("createdAt")
            checksum = manifest.get("sha256")
            reason = manifest.get("reason")
            if (
                not isinstance(created_at, str)
                or not isinstance(checksum, str)
                or not isinstance(reason, str)
            ):
                continue
            if dump_path.stat().st_size != manifest.get("bytes"):
                continue
            if not self._checksum_matches(dump_path, checksum):
                continue
            records.append(
                {
                    "filename": filename,
                    "createdAt": created_at,
                    "bytes": dump_path.stat().st_size,
                    "sha256": checksum,
                    "reason": reason,
                }
            )
        records.sort(key=lambda record: str(record["createdAt"]), reverse=True)
        return records[:limit] if limit is not None else records

    def _pending_requests(self) -> bool:
        if not self._requests_root.is_dir():
            return False
        for request_path in self._requests_root.glob("*.json"):
            payload = self._read_json(request_path)
            if payload.get("kind", "backup") == "backup":
                return True
        return False

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial_path = path.with_suffix(f"{path.suffix}.partial")
        partial_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        partial_path.replace(path)

    @staticmethod
    def _checksum_matches(path: Path, expected: str) -> bool:
        try:
            recorded = path.with_suffix(f"{path.suffix}.sha256").read_text(encoding="utf-8")
        except OSError:
            return False
        return recorded.split(maxsplit=1)[0] == expected
