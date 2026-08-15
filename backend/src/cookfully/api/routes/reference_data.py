from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.routes.recipes import idempotency_key
from cookfully.api.schemas.jobs import JobAcceptedResponse, JobResponse
from cookfully.api.schemas.reference_data import (
    ReferenceDataInstallRequest,
    ReferenceDataStatusResponse,
    ReferenceRelease,
)
from cookfully.application.idempotency import IdempotencyService
from cookfully.application.reference_data import ReferenceDataInstallService
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.observability import correlation_id

router = APIRouter(prefix="/reference-data", tags=["Reference Data"])


def reference_data_service(request: Request) -> ReferenceDataInstallService:
    service: ReferenceDataInstallService = request.app.state.reference_data
    return service


def idempotency_service(request: Request) -> IdempotencyService:
    service: IdempotencyService = request.app.state.idempotency
    return service


@router.get(
    "/status", response_model=ReferenceDataStatusResponse, response_model_by_alias=True
)
def get_reference_data_status(
    service: Annotated[ReferenceDataInstallService, Depends(reference_data_service)],
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> ReferenceDataStatusResponse:
    releases, progress = service.status()
    return ReferenceDataStatusResponse(
        available=bool(releases["available"]),
        missing=tuple(releases["missing"]),
        releases=tuple(ReferenceRelease.model_validate(item) for item in releases["releases"]),
        requestedDatasets=None,
        job=JobResponse.from_progress(progress) if progress is not None else None,
    )


@router.post(
    "/install",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
def install_reference_data(
    payload: ReferenceDataInstallRequest,
    service: Annotated[ReferenceDataInstallService, Depends(reference_data_service)],
    idempotency: Annotated[IdempotencyService, Depends(idempotency_service)],
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
    key: Annotated[str, Depends(idempotency_key)],
) -> JobAcceptedResponse:
    decision = idempotency.begin(
        owner_id=owner.id,
        key=key,
        operation="reference_data.install",
        payload=payload.model_dump(mode="json", by_alias=True),
    )
    if decision.replay:
        if decision.response_body is None:
            raise DomainError(
                "idempotency_response_missing", "Stored response is unavailable.", 500
            )
        return JobAcceptedResponse.model_validate(decision.response_body)
    try:
        accepted = service.request(owner.id, payload.datasets, trace_id=correlation_id.get())
        response = JobAcceptedResponse(job_id=accepted.job_id, status=accepted.status)
    except Exception:
        idempotency.abort(owner_id=owner.id, key=key)
        raise
    idempotency.complete(
        owner_id=owner.id,
        key=key,
        response_status=202,
        resource_id=accepted.job_id,
        job_id=accepted.job_id,
        response_body=response.model_dump(mode="json", by_alias=True),
    )
    return response