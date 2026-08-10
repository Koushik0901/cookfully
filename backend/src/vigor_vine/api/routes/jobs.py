from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from vigor_vine.api.dependencies.auth import require_owner
from vigor_vine.application.jobs import JobProgress, JobService
from vigor_vine.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    kind: str
    status: str
    attempt: int = Field(ge=0)
    max_attempts: int = Field(alias="maxAttempts", ge=1)
    progress_current: int | None = Field(alias="progressCurrent", default=None, ge=0)
    progress_total: int | None = Field(alias="progressTotal", default=None, ge=0)
    next_retry_at: datetime | None = Field(alias="nextRetryAt", default=None)
    terminal_deadline_at: datetime = Field(alias="terminalDeadlineAt")
    failure_code: str | None = Field(alias="failureCode", default=None)
    failure_message: str | None = Field(alias="failureMessage", default=None)

    @classmethod
    def from_progress(cls, progress: JobProgress) -> "JobResponse":
        return cls.model_validate(progress, from_attributes=True)


@router.get("/{job_id}", response_model=JobResponse, response_model_by_alias=True)
def get_job(
    job_id: UUID,
    request: Request,
    _: Annotated[OwnerAccount, Depends(require_owner)],
) -> JobResponse:
    jobs: JobService = request.app.state.jobs
    return JobResponse.from_progress(jobs.progress(job_id))
