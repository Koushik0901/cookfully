from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.domain.common import DomainError
from cookfully.domain.food_semantics import FoodSemanticProfile, profile_from_text
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.models.owner_foods import OwnerFood
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset
from cookfully.infrastructure.models.semantic_matching import FoodSemanticIndex
from cookfully.infrastructure.semantic_embeddings import (
    HashingTextEmbedder,
    TextEmbedder,
    create_text_embedder,
)

FOOD_EMBEDDING_JOB_KIND = "food_embedding_index"
FOOD_EMBEDDING_AGGREGATE_TYPE = "food_catalog"
FOOD_EMBEDDING_AGGREGATE_ID = UUID("00000000-0000-7000-8000-000000000002")
EMBEDDING_DIMENSIONS = 384
BATCH_SIZE = 2048


@dataclass(frozen=True, slots=True)
class FoodEmbeddingSummary:
    active: int
    waiting: int
    missing: int
    indexed: int
    total: int
    model_name: str
    model_version: str
    poll_after_seconds: int | None


def _model_key(settings: NutritionIntelligenceSettings | None) -> tuple[str, str, str]:
    if settings is None:
        return "hashing", "hashing", "default"
    return settings.backend, settings.model_name, settings.model_revision or "default"


def _storage_key(settings: NutritionIntelligenceSettings | None) -> tuple[str, str]:
    backend, name, revision = _model_key(settings)
    return f"{backend}:{name}", revision


def embedding_storage_key(settings: NutritionIntelligenceSettings | None) -> tuple[str, str]:
    """Return the model identity used by both the index job and live search."""

    return _storage_key(settings)


def _text(food: FoodReference | OwnerFood) -> str:
    if isinstance(food, FoodReference):
        return " | ".join(value for value in (food.description, food.brand_owner) if value)
    return " | ".join(value for value in (food.display_name, food.brand) if value)


def _profile_payload(profile: FoodSemanticProfile) -> dict[str, object]:
    return {
        "canonical_identity": profile.canonical_identity,
        "category": profile.category,
        "part": profile.part,
        "state": profile.state,
        "preparation": profile.preparation,
        "form": profile.form,
        "dietary_flags": sorted(profile.dietary_flags),
    }


def _input_hash(value: str, source_version: str) -> str:
    return hashlib.sha256(
        json.dumps({"text": value, "sourceVersion": source_version}, sort_keys=True).encode()
    ).hexdigest()


def _pack(vector: tuple[float, ...]) -> bytes:
    return struct.pack(f"!{len(vector)}f", *vector)


def _get_embedder(settings: NutritionIntelligenceSettings | None) -> TextEmbedder:
    backend, model_name, _ = _model_key(settings)
    if backend == "fastembed":
        runtime = get_settings()
        return create_text_embedder(
            model_name=model_name,
            cache_dir=runtime.semantic_matching_model_dir,
            local_files_only=False,
            allow_fallback=False,
        )
    return HashingTextEmbedder(dimensions=EMBEDDING_DIMENSIONS)


def food_embedding_summary(session_factory: sessionmaker[Session]) -> FoodEmbeddingSummary:
    with session_factory() as session:
        settings = session.get(NutritionIntelligenceSettings, 1)
        model_name, model_version = _storage_key(settings)
        total = int(
            session.scalar(
                select(func.count(FoodReference.id))
                .join(ReferenceDataset)
                .where(ReferenceDataset.status == "active")
            )
            or 0
        )
        total += int(
            session.scalar(select(func.count(OwnerFood.id)).where(OwnerFood.is_active.is_(True)))
            or 0
        )
        indexed = int(
            session.scalar(
                select(func.count(FoodSemanticIndex.id)).where(
                    FoodSemanticIndex.active.is_(True),
                    FoodSemanticIndex.model_name == model_name,
                    FoodSemanticIndex.model_version == model_version,
                    FoodSemanticIndex.embedding_vector.is_not(None),
                )
            )
            or 0
        )
        active = int(
            session.scalar(
                select(func.count(ProcessingJob.id)).where(
                    ProcessingJob.kind == FOOD_EMBEDDING_JOB_KIND,
                    ProcessingJob.aggregate_id == FOOD_EMBEDDING_AGGREGATE_ID,
                    ProcessingJob.status == "running",
                )
            )
            or 0
        )
        waiting = int(
            session.scalar(
                select(func.count(ProcessingJob.id)).where(
                    ProcessingJob.kind == FOOD_EMBEDDING_JOB_KIND,
                    ProcessingJob.aggregate_id == FOOD_EMBEDDING_AGGREGATE_ID,
                    ProcessingJob.status.in_(("queued", "retry_wait")),
                )
            )
            or 0
        )
    return FoodEmbeddingSummary(
        active=active,
        waiting=waiting,
        missing=max(total - indexed, 0),
        indexed=indexed,
        total=total,
        model_name=model_name,
        model_version=model_version,
        poll_after_seconds=2 if active or waiting else None,
    )


def accept_food_embedding_job(
    session_factory: sessionmaker[Session], *, scope: str, trace_id: str
) -> UUID:
    with session_factory() as session:
        settings = session.get(NutritionIntelligenceSettings, 1)
    if settings is not None and settings.backend == "fastembed" and settings.last_ready_at is None:
        raise DomainError(
            "embedding_model_not_ready",
            "Download the selected embedding model before rebuilding the food index.",
            409,
        )
    _, model_name, model_version = _model_key(settings)
    digest = hashlib.sha256(
        json.dumps(
            {"scope": scope, "model": model_name, "version": model_version},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    job = JobService(session_factory).accept(
        kind=FOOD_EMBEDDING_JOB_KIND,
        aggregate_type=FOOD_EMBEDDING_AGGREGATE_TYPE,
        aggregate_id=FOOD_EMBEDDING_AGGREGATE_ID,
        input_hash=f"{scope}:{digest}",
        trace_id=trace_id,
    )
    return job.id


def run_food_embedding_job(session_factory: sessionmaker[Session], job_id: UUID) -> None:
    jobs = JobService(session_factory)
    job = jobs.claim(job_id)
    if job.status != "running":
        return
    try:
        with session_factory() as session:
            settings = session.get(NutritionIntelligenceSettings, 1)
            if (
                settings is not None
                and settings.backend == "fastembed"
                and settings.last_ready_at is None
            ):
                jobs.fail_attempt(
                    job_id,
                    "embedding_model_not_ready",
                    retryable=False,
                    safe_message="The selected embedding model is not ready yet.",
                )
                return
            storage_name, storage_version = _storage_key(settings)
            foods: list[tuple[FoodReference | OwnerFood, str]] = [
                (food, release_id)
                for food, release_id in session.execute(
                    select(FoodReference, ReferenceDataset.release_id)
                    .join(ReferenceDataset)
                    .where(ReferenceDataset.status == "active")
                ).all()
            ]
            foods.extend(
                (food, str(food.version))
                for food in session.scalars(select(OwnerFood).where(OwnerFood.is_active.is_(True)))
            )
        scope = "all" if job.input_hash.startswith("all:") else "missing"
        if scope == "all":
            with session_factory.begin() as session:
                session.execute(
                    update(FoodSemanticIndex)
                    .where(
                        FoodSemanticIndex.model_name == storage_name,
                        FoodSemanticIndex.model_version == storage_version,
                    )
                    .values(active=False)
                )
        embedder = _get_embedder(settings)
        jobs.update_progress(job_id, 0, len(foods))
        for start in range(0, len(foods), BATCH_SIZE):
            batch = foods[start : start + BATCH_SIZE]
            vectors = embedder.embed(tuple(_text(food) for food, _ in batch))
            usda_ids = [food.id for food, _ in batch if isinstance(food, FoodReference)]
            owner_ids = [food.id for food, _ in batch if isinstance(food, OwnerFood)]
            with session_factory.begin() as session:
                rows = session.scalars(
                    select(FoodSemanticIndex).where(
                        FoodSemanticIndex.model_name == storage_name,
                        FoodSemanticIndex.model_version == storage_version,
                        or_(
                            FoodSemanticIndex.food_reference_id.in_(usda_ids),
                            FoodSemanticIndex.owner_food_id.in_(owner_ids),
                        ),
                    )
                ).all()
                existing = {(row.food_reference_id or row.owner_food_id): row for row in rows}
                for (food, source_version), vector in zip(batch, vectors, strict=True):
                    digest = _input_hash(_text(food), source_version)
                    row = existing.get(food.id)
                    if (
                        scope == "missing"
                        and row is not None
                        and row.active
                        and row.input_hash == digest
                        and row.embedding_vector is not None
                    ):
                        continue
                    values = {
                        "dimensions": len(vector),
                        "embedding": _pack(vector),
                        "embedding_vector": list(vector),
                        "profile": _profile_payload(profile_from_text(_text(food))),
                        "input_hash": digest,
                        "source_release_id": source_version,
                        "active": True,
                    }
                    if row is None:
                        session.add(
                            FoodSemanticIndex(
                                food_reference_id=(
                                    food.id if isinstance(food, FoodReference) else None
                                ),
                                owner_food_id=food.id if isinstance(food, OwnerFood) else None,
                                model_name=storage_name,
                                model_version=storage_version,
                                **values,
                            )
                        )
                    else:
                        for key, value in values.items():
                            setattr(row, key, value)
            current = min(start + len(batch), len(foods))
            jobs.update_progress(job_id, current, len(foods))
            jobs.heartbeat(job_id)
        jobs.succeed(job_id)
    except Exception as exc:
        jobs.fail_attempt(
            job_id,
            "food_embedding_failed",
            retryable=True,
            safe_message=str(exc)[:240],
        )
