from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
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
    runtime_status: Literal["ready", "configured", "fallback"] = Field(alias="runtimeStatus")


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


def _response(value: NutritionIntelligenceSettings) -> NutritionIntelligenceSettingsResponse:
    return NutritionIntelligenceSettingsResponse(
        backend=value.backend,
        model_name=value.model_name,
        model_revision=value.model_revision,
        concurrency=value.concurrency,
        version=value.version,
        runtime_status="ready" if value.backend == "hashing" else "configured",
    )


@router.get("/settings", response_model=NutritionIntelligenceSettingsResponse)
def get_settings(
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> NutritionIntelligenceSettingsResponse:
    del owner
    service: NutritionIntelligenceService = request.app.state.nutrition_intelligence
    return _response(service.get())


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
    )
    return _response(value)
