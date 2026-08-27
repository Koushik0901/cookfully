from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.infrastructure.database_backups import DatabaseBackupStore
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/database-backups", tags=["Backups"])


class DatabaseBackupRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str
    created_at: datetime = Field(alias="createdAt")
    bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    reason: Literal["schedule", "manual", "host-copy"]


class DatabaseBackupFailure(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    occurred_at: datetime = Field(alias="occurredAt")
    message: str = Field(min_length=1, max_length=500)


class DatabaseBackupStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    storage_mode: Literal["host_bind_mount"] = Field(alias="storageMode")
    schedule: str
    retention_count: int = Field(alias="retentionCount", ge=1)
    backups: tuple[DatabaseBackupRecord, ...]
    latest: DatabaseBackupRecord | None = None
    last_success_at: datetime | None = Field(alias="lastSuccessAt", default=None)
    last_failure: DatabaseBackupFailure | None = Field(alias="lastFailure", default=None)
    pending_manual_request: bool = Field(alias="pendingManualRequest")
    service_heartbeat_at: datetime | None = Field(alias="serviceHeartbeatAt", default=None)


class DatabaseBackupRequested(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(alias="requestId", min_length=32, max_length=32)
    status: Literal["queued"]


def backup_store(request: Request) -> DatabaseBackupStore:
    store: DatabaseBackupStore = request.app.state.database_backups
    return store


@router.get("", response_model=DatabaseBackupStatus, response_model_by_alias=True)
def get_database_backups(
    request: Request,
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
    store: Annotated[DatabaseBackupStore, Depends(backup_store)],
) -> DatabaseBackupStatus:
    settings = request.app.state.settings
    return DatabaseBackupStatus.model_validate(
        store.status(
            schedule=settings.database_backup_schedule,
            retention_count=settings.database_backup_retention_count,
        )
    )


@router.post(
    "/request",
    response_model=DatabaseBackupRequested,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_database_backup(
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
    store: Annotated[DatabaseBackupStore, Depends(backup_store)],
) -> DatabaseBackupRequested:
    return DatabaseBackupRequested(request_id=store.request_now(), status="queued")
