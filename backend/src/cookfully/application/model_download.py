from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobProgress, JobService
from cookfully.domain.common import utc_now
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.semantic_embeddings import create_text_embedder

logger = logging.getLogger(__name__)

MODEL_DOWNLOAD_JOB_KIND = "semantic_model_download"
MODEL_DOWNLOAD_AGGREGATE_TYPE = "nutrition_intelligence"
MODEL_DOWNLOAD_AGGREGATE_ID = UUID("00000000-0000-7000-8000-000000000003")
MODEL_DOWNLOAD_DEADLINE = timedelta(hours=1)


def model_download_input_hash(model_name: str, model_revision: str | None) -> str:
    payload = json.dumps(
        {"modelName": model_name, "modelRevision": model_revision},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def current_model_download_hash(settings: NutritionIntelligenceSettings) -> str:
    return model_download_input_hash(settings.model_name, settings.model_revision)


def accept_model_download_job_in_session(
    session: Session,
    jobs: JobService,
    *,
    model_name: str,
    model_revision: str | None,
    trace_id: str,
) -> UUID:
    """Replace any older download request and enqueue the selected model."""

    now = utc_now()
    input_hash = model_download_input_hash(model_name, model_revision)
    active_jobs = session.scalars(
        select(ProcessingJob)
        .where(
            ProcessingJob.kind == MODEL_DOWNLOAD_JOB_KIND,
            ProcessingJob.aggregate_id == MODEL_DOWNLOAD_AGGREGATE_ID,
            ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
        )
        .with_for_update()
    ).all()
    for active in active_jobs:
        if active.input_hash != input_hash:
            jobs.supersede_in_session(session, active.id, now=now)

    job = jobs.accept_in_session(
        session,
        kind=MODEL_DOWNLOAD_JOB_KIND,
        aggregate_type=MODEL_DOWNLOAD_AGGREGATE_TYPE,
        aggregate_id=MODEL_DOWNLOAD_AGGREGATE_ID,
        input_hash=input_hash,
        trace_id=trace_id,
        now=now,
    )
    job.terminal_deadline_at = now + MODEL_DOWNLOAD_DEADLINE
    return job.id


def supersede_model_download_jobs_in_session(session: Session, jobs: JobService) -> None:
    now = utc_now()
    active_jobs = session.scalars(
        select(ProcessingJob)
        .where(
            ProcessingJob.kind == MODEL_DOWNLOAD_JOB_KIND,
            ProcessingJob.aggregate_id == MODEL_DOWNLOAD_AGGREGATE_ID,
            ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
        )
        .with_for_update()
    ).all()
    for active in active_jobs:
        jobs.supersede_in_session(session, active.id, now=now)


def latest_model_download(
    session_factory: sessionmaker[Session],
) -> JobProgress | None:
    return JobService(session_factory).latest_for_aggregate(
        MODEL_DOWNLOAD_AGGREGATE_TYPE,
        MODEL_DOWNLOAD_AGGREGATE_ID,
    )


def run_model_download_job(session_factory: sessionmaker[Session], job_id: UUID) -> None:
    jobs = JobService(session_factory)
    job = jobs.claim(job_id)
    if job.status != "running":
        return

    with session_factory() as session:
        settings = session.get(NutritionIntelligenceSettings, 1)
        if settings is None or settings.backend != "fastembed":
            jobs.supersede(job_id)
            return
        expected_hash = current_model_download_hash(settings)
        if expected_hash != job.input_hash:
            jobs.supersede(job_id)
            return
        model_name = settings.model_name

    jobs.update_progress(job_id, 0, 1)
    try:
        # This is deliberately fail-closed. A configured semantic backend must
        # never write deterministic hashing vectors under its model identity.
        create_text_embedder(
            model_name=model_name,
            cache_dir=get_settings().semantic_matching_model_dir,
            local_files_only=False,
            allow_fallback=False,
        )
        with session_factory.begin() as session:
            settings = session.get(NutritionIntelligenceSettings, 1)
            if settings is None or current_model_download_hash(settings) != job.input_hash:
                jobs.supersede_in_session(session, job_id)
                return
            settings.last_ready_at = utc_now()
        jobs.update_progress(job_id, 1, 1)
        jobs.succeed(job_id)
    except Exception:
        logger.exception("semantic model download failed", extra={"job_id": str(job_id)})
        with session_factory.begin() as session:
            settings = session.get(NutritionIntelligenceSettings, 1)
            if settings is not None and current_model_download_hash(settings) == job.input_hash:
                settings.last_ready_at = None
        jobs.fail_attempt(
            job_id,
            "model_download_failed",
            retryable=False,
            safe_message="The embedding model could not be downloaded or loaded.",
        )
