from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.application.jobs import JobProgress
from cookfully.application.model_download import latest_model_download
from cookfully.application.nutrition_intelligence import (
    Backend,
    HostCapacity,
    NutritionIntelligenceService,
    estimate_resources,
    fetch_model_metadata,
)
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings

router = APIRouter(prefix="/nutrition-intelligence", tags=["Nutrition Intelligence"])


class NutritionIntelligenceSettingsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    backend: Backend
    model_name: str = Field(alias="modelName")
    model_revision: str | None = Field(alias="modelRevision")
    concurrency: int = Field(ge=1, le=4)
    version: int = Field(ge=1)
    runtime_status: Literal["ready", "configured", "downloading", "failed"] = Field(
        alias="runtimeStatus"
    )
    download_job_id: str | None = Field(alias="downloadJobId", default=None)
    download_job_status: str | None = Field(alias="downloadJobStatus", default=None)
    download_progress_current: int | None = Field(alias="downloadProgressCurrent", default=None)
    download_progress_total: int | None = Field(alias="downloadProgressTotal", default=None)
    download_failure_message: str | None = Field(alias="downloadFailureMessage", default=None)


class NutritionIntelligenceEstimateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    backend: Backend
    model_name: str = Field(alias="modelName", min_length=1, max_length=200)
    concurrency: int = Field(ge=1, le=4)


class NutritionIntelligenceEstimateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    backend: Backend
    model_name: str = Field(alias="modelName")
    model_revision: str | None = Field(alias="modelRevision")
    concurrency: int
    active_food_count: int = Field(alias="activeFoodCount")
    download_bytes: int = Field(alias="downloadBytes")
    disk_bytes: int = Field(alias="diskBytes")
    model_memory_bytes: int = Field(alias="modelMemoryBytes")
    per_job_memory_bytes: int = Field(alias="perJobMemoryBytes")
    total_memory_bytes: int = Field(alias="totalMemoryBytes")
    required_cpu_cores: int = Field(alias="requiredCpuCores")
    available_cpu_cores: int = Field(alias="availableCpuCores")
    available_memory_bytes: int = Field(alias="availableMemoryBytes")
    available_disk_bytes: int = Field(alias="availableDiskBytes")
    memory_headroom_bytes: int = Field(alias="memoryHeadroomBytes")
    status: Literal["safe", "warning", "blocked"]
    warnings: tuple[str, ...]
    estimate_hash: str = Field(alias="estimateHash")


class NutritionIntelligenceSettingsWrite(NutritionIntelligenceEstimateRequest):
    version: int = Field(ge=1)
    estimate_hash: str = Field(alias="estimateHash", min_length=64, max_length=64)


def _response(
    value: NutritionIntelligenceSettings,
    download_job: JobProgress | None = None,
) -> NutritionIntelligenceSettingsResponse:
    progress = download_job
    status = "ready" if value.backend == "hashing" or value.last_ready_at else "configured"
    job_id: str | None = None
    job_status: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    failure_message: str | None = None
    if progress is not None:
        job_id = str(progress.id)
        job_status = progress.status
        progress_current = progress.progress_current
        progress_total = progress.progress_total
        failure_message = progress.failure_message
        if progress.status in {"queued", "running", "retry_wait"}:
            status = "downloading"
        elif progress.status == "failed":
            status = "failed"
        elif progress.status == "succeeded" and value.last_ready_at:
            status = "ready"
    return NutritionIntelligenceSettingsResponse(
        backend=value.backend,
        model_name=value.model_name,
        model_revision=value.model_revision,
        concurrency=value.concurrency,
        version=value.version,
        runtime_status=status,
        download_job_id=job_id,
        download_job_status=job_status,
        download_progress_current=progress_current,
        download_progress_total=progress_total,
        download_failure_message=failure_message,
    )


@router.get("/settings", response_model=NutritionIntelligenceSettingsResponse)
def get_settings(
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> NutritionIntelligenceSettingsResponse:
    del owner
    service: NutritionIntelligenceService = request.app.state.nutrition_intelligence
    return _response(service.get(), latest_model_download(request.app.state.sessions))


@router.post(
    "/estimate",
    response_model=NutritionIntelligenceEstimateResponse,
    response_model_by_alias=True,
)
def estimate(
    payload: NutritionIntelligenceEstimateRequest,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> NutritionIntelligenceEstimateResponse:
    del owner
    service: NutritionIntelligenceService = request.app.state.nutrition_intelligence
    metadata = fetch_model_metadata(payload.model_name) if payload.backend == "fastembed" else None
    value = estimate_resources(
        backend=payload.backend,
        model_name=payload.model_name,
        concurrency=payload.concurrency,
        metadata=metadata,
        capacity=HostCapacity.detect(),
        active_food_count=service.active_food_count(),
    )
    return NutritionIntelligenceEstimateResponse.model_validate(value.as_dict())


@router.put(
    "/settings",
    response_model=NutritionIntelligenceSettingsResponse,
    response_model_by_alias=True,
)
def update_settings(
    payload: NutritionIntelligenceSettingsWrite,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> NutritionIntelligenceSettingsResponse:
    del owner
    service: NutritionIntelligenceService = request.app.state.nutrition_intelligence
    value = service.update(
        backend=payload.backend,
        model_name=payload.model_name,
        concurrency=payload.concurrency,
        expected_version=payload.version,
        estimate_hash=payload.estimate_hash,
        trace_id=request.headers.get("x-request-id", "nutrition-intelligence-settings"),
    )
    return _response(value, latest_model_download(request.app.state.sessions))
