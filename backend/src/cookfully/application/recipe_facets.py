"""Recipe facets from decision models: computed after processing, stored, read with recipes.

One request per recipe asks every facet question at once (diet, cuisine, meal type, effort,
active time, storage, oven). ``domain.recipe_facets.interpret`` turns the answers into tags and
removes diet tags the ingredient list contradicts. Results live in ``recipe_insights`` (kind
``facets``) under a fingerprint of the recipe's input hash, the models and the prompt version, so
they are recomputed only when the recipe or the panel changes. Without answers a recipe simply has
no facets.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import build_decisions
from cookfully.application.openrouter_settings import decisions_config, load_config
from cookfully.domain.decisions import Answers, Ask, Check, Choice, Purpose, Question, Score
from cookfully.domain.recipe_facets import (
    ACTIVE_TIME_LEVELS,
    CUISINES,
    DIETS,
    EFFORT_LEVELS,
    MEAL_TYPES,
    STORAGE,
    FacetTag,
    interpret,
)
from cookfully.infrastructure.models.recipe_insights import RecipeInsight
from cookfully.infrastructure.models.recipes import Recipe

logger = logging.getLogger(__name__)

KIND = "facets"
PROMPT_VERSION = "recipe-facets-v1"
TEXT_LIMIT = 6000


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


def facet_questions() -> dict[str, Question]:
    questions: dict[str, Question] = {
        f"diet_{diet}": Check(
            f"Is this recipe suitable for this diet? {description}",
            "Suitable as written.",
            "Not suitable as written.",
        )
        for diet, description in DIETS.items()
    }
    questions["cuisine"] = Choice("Which cuisine is this recipe?", CUISINES)
    questions["meal_type"] = Choice("What kind of dish is this?", MEAL_TYPES)
    questions["effort"] = Score("How much effort does this recipe take?", EFFORT_LEVELS)
    questions["active_time"] = Score(
        "How much hands-on time does this recipe need (not counting waiting or oven time)?",
        ACTIVE_TIME_LEVELS,
    )
    for key, (question, yes, no) in STORAGE.items():
        questions[key] = Check(question, yes, no)
    return questions


def facet_ask(title: str, ingredients: Sequence[str], steps: Sequence[str]) -> Ask:
    return Ask(
        Purpose.RECIPE_FACETS,
        {
            "title": title,
            "ingredients": "\n".join(ingredients)[:TEXT_LIMIT],
            "steps": "\n".join(steps)[:TEXT_LIMIT],
        },
        facet_questions(),
    )


def fingerprint(input_hash: str | None, models: Sequence[str]) -> str:
    blob = json.dumps([PROMPT_VERSION, input_hash, list(models)])
    return hashlib.sha256(blob.encode()).hexdigest()


def refresh_recipe_facets(
    session_factory: sessionmaker[Session],
    recipe_id: UUID,
    *,
    decisions: DecisionAsker | None = None,
) -> int:
    """Bring a recipe's facets up to date; returns the number of tags stored. Idempotent."""

    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None:
            return 0
        config = decisions_config(load_config(session))
        models = config.feature(Purpose.RECIPE_FACETS).models
        current = fingerprint(recipe.input_hash, models)
        stored = _stored(session, [recipe_id]).get(recipe_id)
        if stored is not None and stored.fingerprint == current and stored.status == "checked":
            return len(stored.payload.get("tags") or [])
        engine = decisions or build_decisions(session_factory, config)
        active = getattr(engine, "active", None)
        if callable(active) and not active(Purpose.RECIPE_FACETS):
            return 0
        lines = [item.original_text for item in recipe.ingredients]
        steps = [item.text for item in recipe.instructions]
        [answers] = engine.ask([facet_ask(recipe.title, lines, steps)])
        tags = interpret(answers, lines) if answers else ()
        status = "checked" if answers else "not_checked"
        recipe_hash = recipe.input_hash
    with session_factory.begin() as session:
        row = _stored(session, [recipe_id]).get(recipe_id)
        if row is None:
            row = RecipeInsight(recipe_id=recipe_id, kind=KIND)
            session.add(row)
        row.fingerprint = current
        row.status = status
        row.payload = {
            "inputHash": recipe_hash,
            "tags": [{"key": tag.key, "probability": str(tag.probability)} for tag in tags],
        }
    return len(tags)


def stored_facets(session: Session, recipes: Iterable[Recipe]) -> dict[UUID, tuple[FacetTag, ...]]:
    """Fresh facets for each recipe that has them (stale or failed results are left out)."""

    by_id = {recipe.id: recipe for recipe in recipes}
    if not by_id:
        return {}
    models = decisions_config(load_config(session)).feature(Purpose.RECIPE_FACETS).models
    result: dict[UUID, tuple[FacetTag, ...]] = {}
    for recipe_id, row in _stored(session, list(by_id)).items():
        if row.status != "checked":
            continue
        if row.fingerprint != fingerprint(by_id[recipe_id].input_hash, models):
            continue
        tags: list[FacetTag] = []
        for entry in row.payload.get("tags") or []:
            try:
                tags.append(FacetTag(str(entry["key"]), Decimal(str(entry["probability"]))))
            except (KeyError, TypeError, InvalidOperation):
                continue
        result[recipe_id] = tuple(tags)
    return result


def _stored(session: Session, recipe_ids: Sequence[UUID]) -> dict[UUID, RecipeInsight]:
    rows = session.scalars(
        select(RecipeInsight).where(
            RecipeInsight.recipe_id.in_(recipe_ids), RecipeInsight.kind == KIND
        )
    ).all()
    return {row.recipe_id: row for row in rows}
