from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application import model_download
from cookfully.application.jobs import JobService
from cookfully.application.model_download import accept_model_download_job_in_session
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings


def test_ready_model_queues_a_full_food_index_rebuild(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        model_download,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    with session_factory.begin() as session:
        settings = NutritionIntelligenceSettings(
            id=1,
            backend="fastembed",
            model_name="BAAI/bge-small-en-v1.5",
            model_revision="revision-one",
            last_ready_at=None,
        )
        session.add(settings)
        session.flush()
        jobs = JobService(session_factory)
        job_id = accept_model_download_job_in_session(
            session,
            jobs,
            model_name=settings.model_name,
            model_revision=settings.model_revision,
            trace_id="trace-model-download",
        )

    monkeypatch.setattr(model_download, "create_text_embedder", lambda **_: object())
    model_download.run_model_download_job(session_factory, job_id)

    with session_factory() as session:
        model_job = session.get(ProcessingJob, job_id)
        assert model_job is not None and model_job.status == "succeeded"
        assert (
            session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.kind == "food_embedding_index",
                    ProcessingJob.aggregate_type == "food_catalog",
                    ProcessingJob.status == "queued",
                )
            )
            is not None
        )
        ready = session.get(NutritionIntelligenceSettings, 1)
        assert ready is not None and ready.last_ready_at is not None
