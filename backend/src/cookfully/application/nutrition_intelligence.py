from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.application.model_download import (
    accept_model_download_job_in_session,
    supersede_model_download_jobs_in_session,
)
from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset

Backend = Literal["hashing", "fastembed"]
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
HASHING_MODEL = "deterministic-hashing-128"
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
MAX_CONCURRENCY = 4
MEBIBYTE = 1024**2


@dataclass(frozen=True, slots=True)
class HostCapacity:
    cpu_cores: int
    memory_bytes: int
    disk_free_bytes: int

    @classmethod
    def detect(cls, path: Path = Path()) -> HostCapacity:
        memory = 8 * 1024**3
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text(encoding="ascii").splitlines():
                if line.startswith("MemTotal:"):
                    memory = int(line.split()[1]) * 1024
                    break
        return cls(
            cpu_cores=max(1, os.cpu_count() or 1),
            memory_bytes=memory,
            disk_free_bytes=shutil.disk_usage(path).free,
        )


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    revision: str
    download_bytes: int
    parameter_count: int
    dimensions: int


@dataclass(frozen=True, slots=True)
class ResourceEstimate:
    backend: Backend
    model_name: str
    model_revision: str | None
    concurrency: int
    active_food_count: int
    download_bytes: int
    disk_bytes: int
    model_memory_bytes: int
    per_job_memory_bytes: int
    total_memory_bytes: int
    required_cpu_cores: int
    available_cpu_cores: int
    available_memory_bytes: int
    available_disk_bytes: int
    memory_headroom_bytes: int
    status: Literal["safe", "warning", "blocked"]
    warnings: tuple[str, ...]
    estimate_hash: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def validate_model_name(value: str) -> str:
    normalized = value.strip()
    if not MODEL_ID_RE.fullmatch(normalized):
        raise DomainError(
            "invalid_model_name",
            "Use a Hugging Face model name such as organization/model.",
            422,
        )
    return normalized


def estimate_resources(
    *,
    backend: Backend,
    model_name: str,
    concurrency: int,
    metadata: ModelMetadata | None,
    capacity: HostCapacity,
    active_food_count: int,
) -> ResourceEstimate:
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        raise DomainError("invalid_concurrency", "Concurrency must be between 1 and 4.", 422)
    if active_food_count < 0:
        raise DomainError("invalid_food_count", "Active food count cannot be negative.", 422)
    model_name = validate_model_name(model_name) if backend == "fastembed" else HASHING_MODEL
    dimensions = metadata.dimensions if metadata is not None else 128
    download_bytes = metadata.download_bytes if backend == "fastembed" and metadata else 0
    model_memory_bytes = (
        max(128 * MEBIBYTE, download_bytes * 2) if backend == "fastembed" else 32 * MEBIBYTE
    )
    vector_bytes = active_food_count * dimensions * 4
    per_job_memory_bytes = 8 * MEBIBYTE + math.ceil(vector_bytes * 1.25)
    total_memory_bytes = model_memory_bytes + (per_job_memory_bytes * concurrency)
    required_cpu_cores = 1 if backend == "hashing" else concurrency
    warnings: list[str] = []
    if backend == "fastembed" and metadata is None:
        warnings.append("Model metadata could not be verified; the estimate is conservative.")
    if required_cpu_cores > capacity.cpu_cores:
        warnings.append(
            f"This configuration requests {required_cpu_cores} CPU cores, "
            f"but only {capacity.cpu_cores} are available."
        )
    if total_memory_bytes > capacity.memory_bytes:
        warnings.append("Estimated memory exceeds available system memory.")
    elif total_memory_bytes > capacity.memory_bytes * 0.75:
        warnings.append("Estimated memory leaves less than 25% headroom for the application.")
    if download_bytes > capacity.disk_free_bytes:
        warnings.append("The model download is larger than available disk space.")
    status: Literal["safe", "warning", "blocked"] = "safe"
    if required_cpu_cores > capacity.cpu_cores or total_memory_bytes > capacity.memory_bytes:
        status = "blocked"
    elif warnings:
        status = "warning"
    payload = {
        "backend": backend,
        "modelName": model_name,
        "modelRevision": metadata.revision if metadata else None,
        "concurrency": concurrency,
        "activeFoodCount": active_food_count,
        "downloadBytes": download_bytes,
        "totalMemoryBytes": total_memory_bytes,
        "requiredCpuCores": required_cpu_cores,
    }
    estimate_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ResourceEstimate(
        backend=backend,
        model_name=model_name,
        model_revision=metadata.revision if metadata else None,
        concurrency=concurrency,
        active_food_count=active_food_count,
        download_bytes=download_bytes,
        disk_bytes=download_bytes,
        model_memory_bytes=model_memory_bytes,
        per_job_memory_bytes=per_job_memory_bytes,
        total_memory_bytes=total_memory_bytes,
        required_cpu_cores=required_cpu_cores,
        available_cpu_cores=capacity.cpu_cores,
        available_memory_bytes=capacity.memory_bytes,
        available_disk_bytes=capacity.disk_free_bytes,
        memory_headroom_bytes=capacity.memory_bytes - total_memory_bytes,
        status=status,
        warnings=tuple(warnings),
        estimate_hash=estimate_hash,
    )


def fetch_model_metadata(model_name: str) -> ModelMetadata:
    model_name = validate_model_name(model_name)
    try:
        response = httpx.get(
            f"https://huggingface.co/api/models/{model_name}",
            params={"expand[]": "safetensors"},
            timeout=8,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        safe = payload.get("safetensors") or {}
        parameters = safe.get("parameters") or {}
        total = int(safe.get("total") or 0)
        parameter_count = sum(int(value) for value in parameters.values())
        if total <= 0 or parameter_count <= 0:
            raise ValueError("Hugging Face response did not include model size metadata")
        return ModelMetadata(
            revision=str(payload.get("sha") or "main"),
            download_bytes=total,
            parameter_count=parameter_count,
            dimensions=384,
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        raise DomainError(
            "model_metadata_unavailable",
            "Hugging Face model metadata could not be verified.",
            422,
        ) from exc


class NutritionIntelligenceService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self) -> NutritionIntelligenceSettings:
        with self._session_factory() as session:
            value = session.get(NutritionIntelligenceSettings, 1)
            if value is None:
                value = NutritionIntelligenceSettings(id=1)
                session.add(value)
                session.commit()
            session.expunge(value)
            return value

    def active_food_count(self) -> int:
        with self._session_factory() as session:
            return int(
                session.scalar(
                    select(func.count(FoodReference.id))
                    .join(FoodReference.dataset)
                    .where(ReferenceDataset.status == "active")
                )
                or 0
            )

    def update(
        self,
        *,
        backend: Backend,
        model_name: str,
        concurrency: int,
        expected_version: int,
        estimate_hash: str,
        trace_id: str = "nutrition-intelligence-settings",
    ) -> NutritionIntelligenceSettings:
        jobs = JobService(self._session_factory)
        with self._session_factory.begin() as session:
            value = session.scalar(
                select(NutritionIntelligenceSettings).where(NutritionIntelligenceSettings.id == 1)
            )
            if value is None:
                value = NutritionIntelligenceSettings(id=1)
                session.add(value)
                session.flush()
            if value.version != expected_version:
                raise DomainError("stale_settings", "Settings changed while you were editing.", 409)
            metadata = fetch_model_metadata(model_name) if backend == "fastembed" else None
            active_food_count = self.active_food_count()
            estimate = estimate_resources(
                backend=backend,
                model_name=model_name,
                concurrency=concurrency,
                metadata=metadata,
                capacity=HostCapacity.detect(),
                active_food_count=active_food_count,
            )
            if estimate.estimate_hash != estimate_hash:
                raise DomainError(
                    "stale_resource_estimate",
                    "Resource requirements changed; review the estimate again.",
                    409,
                )
            if estimate.status == "blocked":
                raise DomainError(
                    "resource_limit_exceeded",
                    "This model and concurrency exceed the available system capacity.",
                    422,
                )
            value.backend = backend
            value.model_name = model_name if backend == "fastembed" else DEFAULT_MODEL
            value.model_revision = estimate.model_revision
            value.concurrency = concurrency
            value.last_ready_at = None
            value.version += 1
            if backend == "fastembed":
                accept_model_download_job_in_session(
                    session,
                    jobs,
                    model_name=value.model_name,
                    model_revision=value.model_revision,
                    trace_id=trace_id,
                )
            else:
                supersede_model_download_jobs_in_session(session, jobs)
                value.last_ready_at = utc_now()
            session.flush()
            session.expunge(value)
            return value
