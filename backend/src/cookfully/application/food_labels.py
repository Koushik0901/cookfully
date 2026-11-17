"""Label every USDA reference food once with decision models, as a resumable background job.

Per food the panel answers, in one request: its state (raw, cooked, dried, canned, frozen,
prepared), whether it is generic, processed or branded, plant or animal origin, whether it is a
flavoured or seasoned variant, and common allergens. Labels are stored in ``food_labels`` under a
fingerprint of the description, the models and the prompt version, so a rerun only asks about new
or changed foods. The matcher reads them as compatibility signals (no model calls while matching).
The job stops cleanly, reporting why, when the engine stops answering (spend cap reached or the
feature switched off).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import build_decisions
from cookfully.application.jobs import JobService
from cookfully.application.openrouter_settings import decisions_config, load_config
from cookfully.domain.common import DomainError
from cookfully.domain.decisions import Answers, Ask, Check, Choice, Purpose, Question
from cookfully.domain.food_labels import FoodLabels
from cookfully.infrastructure.models.food_labels import FoodLabel
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset

logger = logging.getLogger(__name__)

JOB_KIND = "food_labeling"
AGGREGATE_TYPE = "food_catalog"
AGGREGATE_ID = UUID("00000000-0000-7000-8000-000000000003")
PROMPT_VERSION = "food-labels-v1"
BATCH_SIZE = 40

STATES: Mapping[str, str] = {
    "raw": "Raw or fresh, as bought (uncooked meat, fresh produce, dry grains and pasta).",
    "cooked": "Cooked: boiled, baked, roasted, fried, grilled, steamed or prepared.",
    "dried": "Dried or dehydrated (dried fruit, powders).",
    "canned": "Canned or jarred.",
    "frozen": "Frozen.",
    "not_applicable": "None of these apply (oils, sugars, drinks, condiments).",
}
KINDS: Mapping[str, str] = {
    "generic": "A plain, generic food.",
    "processed": "A processed or mixed product (sauces, snacks, prepared dishes).",
    "branded": "A branded or restaurant item.",
}
ORIGINS: Mapping[str, str] = {
    "plant": "From plants.",
    "animal": "From animals (meat, fish, dairy, eggs).",
    "mixed": "A mix of plant and animal ingredients.",
}
ALLERGENS = ("dairy", "egg", "gluten", "tree_nuts", "peanuts", "soy", "fish", "shellfish")


def label_questions() -> dict[str, Question]:
    questions: dict[str, Question] = {
        "state": Choice("What state is this food in, as described?", STATES),
        "kind": Choice("What kind of food entry is this?", KINDS),
        "origin": Choice("Where does this food come from?", ORIGINS),
        "flavored": Check(
            "Is this a flavoured, sweetened, seasoned or coated variant of a basic food?",
            "A flavoured or seasoned variant.",
            "The plain food.",
        ),
    }
    for allergen in ALLERGENS:
        name = allergen.replace("_", " ")
        questions[f"contains_{allergen}"] = Check(
            f"Does this food contain {name}?", f"Contains {name}.", f"No {name}."
        )
    return questions


def label_ask(food: FoodReference) -> Ask:
    return Ask(
        Purpose.FOOD_LABELS,
        {"food": food.description, "category": food.food_category or ""},
        label_questions(),
    )


def labels_from(answers: Answers) -> dict[str, Any] | None:
    """Compact JSON labels, or ``None`` when nothing usable came back."""

    if not answers:
        return None
    result: dict[str, Any] = {}
    for question in ("state", "kind", "origin"):
        top = answers.top(question)
        if top is not None:
            probability = (answers.choice(question) or {})[top]
            result[question] = [top, str(round(probability, 4))]
    flavored = answers.check("flavored")
    if flavored is not None:
        result["flavored"] = str(round(flavored, 4))
    allergens = {
        allergen: str(round(value, 4))
        for allergen in ALLERGENS
        if (value := answers.check_worst(f"contains_{allergen}")) is not None
    }
    if allergens:
        result["allergens"] = allergens
    return result or None


def fingerprint(food: FoodReference, models: Sequence[str]) -> str:
    blob = json.dumps(
        [PROMPT_VERSION, food.description, food.food_category, list(models)], sort_keys=True
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def load_labels(session: Session, food_ids: Iterable[UUID]) -> dict[UUID, FoodLabels]:
    ids = list(dict.fromkeys(food_ids))
    if not ids:
        return {}
    rows = session.scalars(select(FoodLabel).where(FoodLabel.food_reference_id.in_(ids))).all()
    return {row.food_reference_id: FoodLabels.from_json(row.labels) for row in rows}


@dataclass(frozen=True, slots=True)
class FoodLabelSummary:
    labelled: int
    total: int
    active: int
    waiting: int


def food_label_summary(session_factory: sessionmaker[Session]) -> FoodLabelSummary:
    with session_factory() as session:
        total = int(
            session.scalar(
                select(func.count(FoodReference.id))
                .join(ReferenceDataset)
                .where(ReferenceDataset.status == "active")
            )
            or 0
        )
        labelled = int(
            session.scalar(
                select(func.count(FoodLabel.food_reference_id))
                .join(FoodReference, FoodReference.id == FoodLabel.food_reference_id)
                .join(ReferenceDataset)
                .where(ReferenceDataset.status == "active")
            )
            or 0
        )
        statuses: dict[str, int] = {
            str(status): int(count)
            for status, count in session.execute(
                select(ProcessingJob.status, func.count(ProcessingJob.id))
                .where(ProcessingJob.kind == JOB_KIND, ProcessingJob.aggregate_id == AGGREGATE_ID)
                .group_by(ProcessingJob.status)
            ).all()
        }
    return FoodLabelSummary(
        labelled=labelled,
        total=total,
        active=int(statuses.get("running", 0)),
        waiting=int(statuses.get("queued", 0)) + int(statuses.get("retry_wait", 0)),
    )


def accept_food_label_job(session_factory: sessionmaker[Session], *, trace_id: str) -> UUID:
    with session_factory() as session:
        config = decisions_config(load_config(session))
    if not config.active(Purpose.FOOD_LABELS):
        raise DomainError(
            "food_labels_unavailable",
            "Save an OpenRouter key and switch Food labels on to label foods.",
            409,
        )
    job = JobService(session_factory).accept(
        kind=JOB_KIND,
        aggregate_type=AGGREGATE_TYPE,
        aggregate_id=AGGREGATE_ID,
        input_hash=f"{PROMPT_VERSION}:{','.join(config.feature(Purpose.FOOD_LABELS).models)}",
        trace_id=trace_id,
    )
    return job.id


def run_food_label_job(
    session_factory: sessionmaker[Session], job_id: UUID, *, decisions: Any = None
) -> None:
    jobs = JobService(session_factory)
    job = jobs.claim(job_id)
    if job.status != "running":
        return
    try:
        engine = decisions or build_decisions(session_factory)
        with session_factory() as session:
            models = decisions_config(load_config(session)).feature(Purpose.FOOD_LABELS).models
            foods = list(
                session.scalars(
                    select(FoodReference)
                    .join(ReferenceDataset)
                    .where(ReferenceDataset.status == "active")
                    .order_by(FoodReference.id)
                )
            )
            stored = {
                row.food_reference_id: row.fingerprint for row in session.scalars(select(FoodLabel))
            }
        pending = [food for food in foods if stored.get(food.id) != fingerprint(food, models)]
        jobs.update_progress(job_id, len(foods) - len(pending), len(foods))
        done = len(foods) - len(pending)
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start : start + BATCH_SIZE]
            results = engine.ask([label_ask(food) for food in batch])
            labelled = [
                (food, labels)
                for food, answers in zip(batch, results, strict=True)
                if (labels := labels_from(answers)) is not None
            ]
            if not labelled:
                jobs.fail_attempt(
                    job_id,
                    "decision_answers_unavailable",
                    retryable=False,
                    safe_message=(
                        "Labelling stopped: the decision models stopped answering (spend cap "
                        "reached, key missing or feature off). Run it again to resume."
                    ),
                )
                return
            with session_factory.begin() as session:
                for food, labels in labelled:
                    row = session.get(FoodLabel, food.id)
                    if row is None:
                        row = FoodLabel(food_reference_id=food.id)
                        session.add(row)
                    row.fingerprint = fingerprint(food, models)
                    row.labels = labels
            done += len(batch)
            jobs.update_progress(job_id, done, len(foods))
        jobs.succeed(job_id)
    except Exception:
        logger.exception("Food labelling job failed.")
        jobs.fail_attempt(
            job_id,
            "food_labeling_failed",
            retryable=True,
            safe_message="Food labelling failed safely; run it again to resume.",
        )
