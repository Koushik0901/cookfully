from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.repositories.nutrition import NutritionRepository


@dataclass(frozen=True, slots=True)
class NutritionRecovery:
    recipe_id: UUID
    title: str
    nutrition_state: str
    job_id: UUID | None = None
    skipped_reason: str | None = None


def recover_stale_nutrition(
    session_factory: sessionmaker[Session], *, dry_run: bool = False
) -> list[NutritionRecovery]:
    """Requeue recipes whose nutrition match was blocked by missing reference data."""

    recoveries: list[NutritionRecovery] = []
    jobs = JobService(session_factory)
    with session_factory.begin() as session:
        active_types = {
            item.dataset_type for item in NutritionRepository(session).active_datasets()
        }
        reference_ready = {"foundation", "sr_legacy"}.issubset(active_types)
        in_flight = set(
            session.scalars(
                select(ProcessingJob.aggregate_id).where(
                    ProcessingJob.kind == "nutrition_match",
                    ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
                )
            )
        )
        candidates = session.scalars(
            select(Recipe).where(
                Recipe.status != "archived",
                Recipe.nutrition_state.in_(("pending", "partial", "failed")),
            )
        ).all()
        for recipe in candidates:
            if recipe.id in in_flight:
                continue
            latest = session.scalar(
                select(ProcessingJob)
                .where(
                    ProcessingJob.kind == "nutrition_match",
                    ProcessingJob.aggregate_id == recipe.id,
                )
                .order_by(ProcessingJob.accepted_at.desc(), ProcessingJob.id.desc())
                .limit(1)
            )
            if (
                latest is None
                or latest.status != "failed"
                or latest.failure_code != "reference_data_unavailable"
            ):
                continue
            if not reference_ready:
                recoveries.append(
                    NutritionRecovery(
                        recipe.id,
                        recipe.title,
                        recipe.nutrition_state,
                        skipped_reason="reference_data_unavailable",
                    )
                )
                continue
            if dry_run:
                recoveries.append(
                    NutritionRecovery(
                        recipe.id,
                        recipe.title,
                        recipe.nutrition_state,
                        skipped_reason="dry_run",
                    )
                )
                continue
            recipe.status = "processing"
            recipe.nutrition_state = "stale"
            recipe.version += 1
            job = jobs.accept_in_session(
                session,
                kind="nutrition_match",
                aggregate_type="recipe",
                aggregate_id=recipe.id,
                input_hash=recipe.input_hash,
                trace_id=f"recover-{uuid7()}",
            )
            recoveries.append(
                NutritionRecovery(recipe.id, recipe.title, recipe.nutrition_state, job_id=job.id)
            )
    return recoveries
