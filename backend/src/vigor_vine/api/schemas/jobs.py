from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from vigor_vine.application.jobs import JobProgress


class JobAcceptedResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: UUID = Field(alias="jobId")
    resource_id: UUID | None = Field(alias="resourceId", default=None)
    status: str = "queued"


class JobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    kind: str
    aggregate_id: UUID = Field(alias="aggregateId")
    status: str
    attempt: int = Field(ge=0)
    max_attempts: int = Field(alias="maxAttempts", ge=1)
    input_hash: str = Field(alias="inputHash")
    progress_current: int | None = Field(alias="progressCurrent", default=None, ge=0)
    progress_total: int | None = Field(alias="progressTotal", default=None, ge=0)
    next_retry_at: datetime | None = Field(alias="nextRetryAt", default=None)
    terminal_deadline_at: datetime = Field(alias="terminalDeadlineAt")
    failure_code: str | None = Field(alias="failureCode", default=None)
    failure_message: str | None = Field(alias="failureMessage", default=None)
    created_at: datetime = Field(alias="createdAt")
    finished_at: datetime | None = Field(alias="finishedAt", default=None)
    poll_after_seconds: int | None = Field(alias="pollAfterSeconds", default=None)
    recovery_actions: tuple[str, ...] = Field(alias="recoveryActions", default=())

    @classmethod
    def from_progress(cls, progress: JobProgress) -> "JobResponse":
        actions: tuple[str, ...] = ()
        if progress.status == "failed":
            actions = ("retry", "edit_recipe", "enter_manual_nutrition")
        elif progress.status == "superseded":
            actions = ("reload",)
        elif progress.status == "retry_wait":
            actions = ("wait", "edit_recipe")
        return cls(
            id=progress.id,
            kind=progress.kind,
            aggregate_id=progress.aggregate_id,
            status=progress.status,
            attempt=progress.attempt,
            max_attempts=progress.max_attempts,
            input_hash=progress.input_hash,
            progress_current=progress.progress_current,
            progress_total=progress.progress_total,
            next_retry_at=progress.next_retry_at,
            terminal_deadline_at=progress.terminal_deadline_at,
            failure_code=progress.failure_code,
            failure_message=progress.failure_message,
            created_at=progress.accepted_at,
            finished_at=progress.finished_at,
            poll_after_seconds=(
                2
                if progress.status not in {"succeeded", "failed", "cancelled", "superseded"}
                else None
            ),
            recovery_actions=actions,
        )
