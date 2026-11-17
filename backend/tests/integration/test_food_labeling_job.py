from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.food_labels import (
    JOB_KIND,
    food_label_summary,
    load_labels,
    run_food_label_job,
)
from cookfully.application.jobs import JobService
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset


def _seed(session_factory: sessionmaker[Session], names: list[str]) -> list[FoodReference]:
    with session_factory.begin() as session:
        dataset = ReferenceDataset(
            dataset_type="sr_legacy",
            release_id="test-release",
            released_on=date(2018, 4, 1),
            imported_at=datetime.now(UTC),
            source_url="https://example.test",
            license="CC0",
            status="active",
        )
        session.add(dataset)
        session.flush()
        foods = [
            FoodReference(
                dataset_id=dataset.id,
                external_id=str(index),
                description=name,
                normalized_name=name.lower(),
                data_type="sr_legacy",
                basis_grams=Decimal(100),
            )
            for index, name in enumerate(names)
        ]
        session.add_all(foods)
    return foods


def _engine(responder: Any) -> tuple[Decisions, ScriptedDecisionTransport]:
    transport = ScriptedDecisionTransport(responder)
    engine = Decisions(
        DecisionsConfig("k", features={Purpose.FOOD_LABELS: FeatureConfig(True, ("m1",))}),
        transport,
        InMemoryDecisionStore(),
    )
    return engine, transport


def _labels(_model: str, state: Any, _questions: Any) -> object:
    cooked = "cooked" in state["food"]
    return {
        "state": {
            "type": "choice",
            "probabilities": {"cooked" if cooked else "raw": 0.9, "frozen": 0.1},
        },
        "kind": {"type": "choice", "probabilities": {"generic": 0.95, "processed": 0.05}},
        "origin": {"type": "choice", "probabilities": {"plant": 1.0}},
        "flavored": {"type": "noul", "noul": 0.05},
        "contains_gluten": {"type": "noul", "noul": 0.02},
    }


def _job(session_factory: sessionmaker[Session], key: str) -> Any:
    return JobService(session_factory).accept(
        kind=JOB_KIND,
        aggregate_type="food_catalog",
        aggregate_id=__import__("uuid").uuid4(),
        input_hash=key,
        trace_id="test",
    )


def test_job_labels_active_foods_and_resumes_without_asking_again(
    session_factory: sessionmaker[Session],
) -> None:
    foods = _seed(session_factory, ["Rice, white, raw", "Rice, white, cooked"])
    engine, transport = _engine(_labels)
    job = _job(session_factory, "first")
    run_food_label_job(session_factory, job.id, decisions=engine)
    with session_factory() as session:
        assert (
            session.scalar(select(ProcessingJob.status).where(ProcessingJob.id == job.id))
            == "succeeded"
        )
        labels = load_labels(session, [food.id for food in foods])
    assert labels[foods[0].id].state == "raw"
    assert labels[foods[1].id].state == "cooked"
    assert labels[foods[1].id].state_probability == Decimal("0.9")
    assert food_label_summary(session_factory).labelled == 2
    calls = len(transport.calls)

    run_food_label_job(session_factory, _job(session_factory, "second").id, decisions=engine)
    assert len(transport.calls) == calls  # nothing new to ask


def test_job_stops_cleanly_when_the_models_stop_answering(
    session_factory: sessionmaker[Session],
) -> None:
    _seed(session_factory, ["Kale, raw"])
    engine, _ = _engine(lambda *_args: None)
    job = _job(session_factory, "down")
    run_food_label_job(session_factory, job.id, decisions=engine)
    with session_factory() as session:
        row = session.get(ProcessingJob, job.id)
        assert row is not None
        assert row.failure_code == "decision_answers_unavailable"
    assert food_label_summary(session_factory).labelled == 0
