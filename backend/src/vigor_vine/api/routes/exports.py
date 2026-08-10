from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from vigor_vine.api.dependencies.auth import require_browser_owner
from vigor_vine.api.routes.recipes import idempotency_key
from vigor_vine.api.schemas.jobs import JobAcceptedResponse
from vigor_vine.application.exports import ExportJobService
from vigor_vine.application.idempotency import IdempotencyService
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.infrastructure.observability import correlation_id

router = APIRouter(prefix="/exports", tags=["Data Ownership", "Jobs"])


class ExportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    include_media: bool = Field(alias="includeMedia", default=True)


def export_service(request: Request) -> ExportJobService:
    service: ExportJobService = request.app.state.exports
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.post(
    "",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_portable_export(
    payload: ExportRequest,
    request: Request,
    service: Annotated[ExportJobService, Depends(export_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    body = payload.model_dump(mode="json", by_alias=True)
    decision = idempotency.begin(
        owner_id=owner.id, key=key, operation="export.create", payload=body
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        job = service.request(
            owner.id,
            include_media=payload.include_media,
            trace_id=correlation_id.get(),
        )
        response = JobAcceptedResponse(job_id=job.id, resource_id=owner.id, status=job.status)
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=202,
        resource_id=owner.id,
        job_id=job.id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response


@router.get("/{jobId}/download", response_class=FileResponse)
def download_portable_export(
    job_id: Annotated[UUID, Path(alias="jobId")],
    service: Annotated[ExportJobService, Depends(export_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> FileResponse:
    archive = service.claim_download(owner.id, job_id)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename="vigor-vine-portable-export.zip",
    )
