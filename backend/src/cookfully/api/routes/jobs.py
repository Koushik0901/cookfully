from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.schemas.jobs import JobResponse
from cookfully.application.jobs import JobService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/current", response_model=JobResponse, response_model_by_alias=True)
def get_current_job(
    aggregate_type: Annotated[str, Query(alias="aggregateType", min_length=1, max_length=80)],
    aggregate_id: Annotated[UUID, Query(alias="aggregateId")],
    request: Request,
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> JobResponse:
    jobs: JobService = request.app.state.jobs
    progress = jobs.latest_for_aggregate(aggregate_type, aggregate_id)
    if progress is None:
        raise DomainError("job_not_found", "Job was not found.", 404)
    return JobResponse.from_progress(progress)


@router.get("/{jobId}", response_model=JobResponse, response_model_by_alias=True)
def get_job(
    job_id: Annotated[UUID, Path(alias="jobId")],
    request: Request,
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> JobResponse:
    jobs: JobService = request.app.state.jobs
    return JobResponse.from_progress(jobs.progress(job_id))
