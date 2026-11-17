"""Per-recipe taste scores for meal suggestions, computed ahead of time from decision models.

For each recipe the panel answers "does this make a satisfying, complete meal?" and, when the owner
has favourites, "would someone who loves these recipes enjoy this one?". The score (0 to 1) is
stored in ``recipe_insights`` (kind ``taste``) under a fingerprint of the recipe, the favourites,
the models and the prompt version. The suggestion solver reads stored scores only, so its result is
deterministic for a fixed set of scores; recipes without a score are treated as neutral.
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
from cookfully.domain.decisions import Answers, Ask, Check, Purpose, Question
from cookfully.infrastructure.models.recipe_insights import RecipeInsight
from cookfully.infrastructure.models.recipes import Recipe

logger = logging.getLogger(__name__)

KIND = "taste"
PROMPT_VERSION = "taste-v1"
MAX_LIKED = 8
TEXT_LIMIT = 4000
# Taste weighs twice as much as "satisfying meal" when both are known.
LIKE_WEIGHT = Decimal(2)

SATISFYING = (
    "Does this recipe make a satisfying, complete meal that people would be happy to eat for "
    "lunch or dinner?"
)
LIKE = (
    "The cook loves the recipes listed in liked_recipes. Would they probably enjoy this recipe "
    "too, judging by its ingredients, flavours and style?"
)


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


def liked_titles(session: Session) -> tuple[str, ...]:
    """Up to ``MAX_LIKED`` favourite recipe titles, in a stable order."""

    titles = session.scalars(
        select(Recipe.title)
        .where(Recipe.is_favorite.is_(True), Recipe.status != "archived")
        .order_by(Recipe.updated_at.desc(), Recipe.id)
        .limit(MAX_LIKED)
    ).all()
    return tuple(sorted(titles))


def taste_ask(title: str, ingredients: Sequence[str], liked: Sequence[str]) -> Ask:
    questions: dict[str, Question] = {
        "satisfying": Check(SATISFYING, "A satisfying meal.", "Not really a meal on its own.")
    }
    state = {"title": title, "ingredients": "\n".join(ingredients)[:TEXT_LIMIT]}
    if liked:
        questions["like"] = Check(
            LIKE, "They would probably enjoy it.", "Probably not their taste."
        )
        state["liked_recipes"] = "\n".join(liked)
    return Ask(Purpose.RECIPE_FACETS, state, questions)


def score_from(answers: Answers) -> Decimal | None:
    satisfying = answers.check("satisfying")
    like = answers.check("like")
    if like is not None and satisfying is not None:
        return (LIKE_WEIGHT * like + satisfying) / (LIKE_WEIGHT + 1)
    return like if like is not None else satisfying


def fingerprint(input_hash: str | None, liked: Sequence[str], models: Sequence[str]) -> str:
    blob = json.dumps([PROMPT_VERSION, input_hash, list(liked), list(models)])
    return hashlib.sha256(blob.encode()).hexdigest()


def refresh_taste_score(
    session_factory: sessionmaker[Session],
    recipe_id: UUID,
    *,
    decisions: DecisionAsker | None = None,
) -> Decimal | None:
    """Bring a recipe's stored score up to date; returns it. Idempotent."""

    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None:
            return None
        config = decisions_config(load_config(session))
        models = config.feature(Purpose.RECIPE_FACETS).models
        liked = liked_titles(session)
        current = fingerprint(recipe.input_hash, liked, models)
        stored = _stored(session, [recipe_id]).get(recipe_id)
        if stored is not None and stored.fingerprint == current and stored.status == "checked":
            return _score(stored)
        engine = decisions or build_decisions(session_factory, config)
        active = getattr(engine, "active", None)
        if callable(active) and not active(Purpose.RECIPE_FACETS):
            return None
        lines = [item.original_text for item in recipe.ingredients]
        [answers] = engine.ask([taste_ask(recipe.title, lines, liked)])
        score = score_from(answers)
    with session_factory.begin() as session:
        row = _stored(session, [recipe_id]).get(recipe_id)
        if row is None:
            row = RecipeInsight(recipe_id=recipe_id, kind=KIND)
            session.add(row)
        row.fingerprint = current
        row.status = "checked" if score is not None else "not_checked"
        row.payload = {"score": str(round(score, 4)) if score is not None else None}
    return score


def refresh_all_taste_scores(session_factory: sessionmaker[Session]) -> int:
    """Recheck every recipe's score (after favourites change); returns how many ran."""

    with session_factory() as session:
        recipe_ids = list(session.scalars(select(Recipe.id).where(Recipe.status != "archived")))
    decisions = build_decisions(session_factory)
    for recipe_id in recipe_ids:
        try:
            refresh_taste_score(session_factory, recipe_id, decisions=decisions)
        except Exception:
            logger.exception("Taste score refresh failed for a recipe.")
    return len(recipe_ids)


def stored_taste_scores(session: Session, recipe_ids: Iterable[UUID]) -> dict[UUID, Decimal]:
    """Fresh stored scores; stale or missing ones are left out (neutral for the solver)."""

    ids = list(recipe_ids)
    if not ids:
        return {}
    recipes = {
        recipe.id: recipe for recipe in session.scalars(select(Recipe).where(Recipe.id.in_(ids)))
    }
    models = decisions_config(load_config(session)).feature(Purpose.RECIPE_FACETS).models
    liked = liked_titles(session)
    result: dict[UUID, Decimal] = {}
    for recipe_id, row in _stored(session, ids).items():
        recipe = recipes.get(recipe_id)
        if recipe is None or row.status != "checked":
            continue
        if row.fingerprint != fingerprint(recipe.input_hash, liked, models):
            continue
        score = _score(row)
        if score is not None:
            result[recipe_id] = score
    return result


def _score(row: RecipeInsight) -> Decimal | None:
    raw = row.payload.get("score")
    try:
        return Decimal(str(raw)) if raw is not None else None
    except InvalidOperation:
        return None


def _stored(session: Session, recipe_ids: Sequence[UUID]) -> dict[UUID, RecipeInsight]:
    rows = session.scalars(
        select(RecipeInsight).where(
            RecipeInsight.recipe_id.in_(recipe_ids), RecipeInsight.kind == KIND
        )
    ).all()
    return {row.recipe_id: row for row in rows}
