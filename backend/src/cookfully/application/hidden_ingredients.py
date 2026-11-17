"""Model-based warnings for avoid-list items an ingredient may contain without naming them.

For each ingredient and each avoid-list item the line does not already name, the panel answers
"could this contain it?" (Worcestershire sauce and anchovy). The most cautious answer across models
is used and a line is flagged at or above ``THRESHOLD``, erring towards a warning. These warnings
only ever add to the deterministic ones in ``domain.avoid_list``.

Results are stored per recipe in ``recipe_insights`` under a fingerprint of the recipe input, the
avoid list, the models and the prompt version. A recipe whose stored result does not match, or
whose check failed, reads as "not checked", never as "safe".
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.avoid_warnings import ingredient_warnings, owner_avoid_list
from cookfully.application.decisions import build_decisions
from cookfully.application.openrouter_settings import decisions_config, load_config
from cookfully.domain.avoid_list import AvoidWarning
from cookfully.domain.decisions import Answers, Ask, Check, Purpose
from cookfully.infrastructure.models.recipe_insights import RecipeInsight
from cookfully.infrastructure.models.recipes import Recipe

logger = logging.getLogger(__name__)

KIND = "hidden_ingredients"
PROMPT_VERSION = "hidden-ingredients-v1"
THRESHOLD = Decimal("0.5")
INSTRUCTIONS = (
    "Could this recipe ingredient contain, or commonly be made with, {item}? Answer yes when "
    "typical versions of it do, even if the line does not name it (for example, Worcestershire "
    "sauce usually contains anchovy, and pesto usually contains pine nuts and parmesan). Answer no "
    "only when it normally does not."
)
CHECKED = "checked"
NOT_CHECKED = "not_checked"
NO_LIST = "no_avoid_list"


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


@dataclass(frozen=True, slots=True)
class HiddenLine:
    ingredient_id: UUID
    text: str


@dataclass(frozen=True, slots=True)
class HiddenCheck:
    status: str
    flags: tuple[AvoidWarning, ...]


def check_hidden(
    decisions: DecisionAsker,
    *,
    recipe_title: str,
    lines: Sequence[HiddenLine],
    avoid: Sequence[str],
    already: frozenset[tuple[UUID, str]] = frozenset(),
) -> HiddenCheck:
    """Ask the panel about every (line, item) pair not in ``already``; fail closed on gaps."""

    pending: list[tuple[HiddenLine, dict[str, str]]] = []
    for line in lines:
        keys = {
            f"a{index}": item
            for index, item in enumerate(avoid)
            if (line.ingredient_id, item) not in already
        }
        if keys:
            pending.append((line, keys))
    if not pending:
        return HiddenCheck(CHECKED, ())
    asks = [
        Ask(
            Purpose.HIDDEN_INGREDIENTS,
            {"recipe": recipe_title, "ingredient_line": line.text},
            {
                key: Check(
                    INSTRUCTIONS.format(item=item),
                    f"It may contain {item}.",
                    f"It normally does not contain {item}.",
                )
                for key, item in keys.items()
            },
        )
        for line, keys in pending
    ]
    status = CHECKED
    flags: list[AvoidWarning] = []
    for (line, keys), answers in zip(pending, decisions.ask(asks), strict=True):
        for key, item in keys.items():
            probability = answers.check_worst(key)
            if probability is not None and probability >= THRESHOLD:
                flags.append(AvoidWarning(line.ingredient_id, item, "model", round(probability, 4)))
            elif probability is None:
                status = NOT_CHECKED
    return HiddenCheck(status, tuple(flags))


def input_fingerprint(recipe: Recipe, models: Sequence[str]) -> str:
    """What a stored result's flags depend on besides the avoid list: the recipe and the panel."""

    blob = json.dumps(
        [
            PROMPT_VERSION,
            recipe.input_hash,
            [(item.id.hex, item.original_text, item.food_name) for item in recipe.ingredients],
            list(models),
        ],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def fingerprint(recipe: Recipe, avoid: Sequence[str], models: Sequence[str]) -> str:
    blob = json.dumps([input_fingerprint(recipe, models), sorted(avoid)], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _flags_from(payload: dict[str, object]) -> list[AvoidWarning]:
    flags: list[AvoidWarning] = []
    raw = payload.get("flags")
    for entry in raw if isinstance(raw, list) else []:
        try:
            flags.append(
                AvoidWarning(
                    UUID(entry["ingredientId"]),
                    str(entry["item"]),
                    "model",
                    Decimal(entry["probability"]),
                )
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue
    return flags


def _still_valid(
    previous: RecipeInsight | None, input_fp: str, avoid: Sequence[str]
) -> list[AvoidWarning]:
    """Earlier model warnings that still apply: same recipe and panel, item still avoided.

    A warning is only dropped when it is proven wrong (the recipe changed, or the owner no longer
    avoids the item), never because a later check could not run.
    """

    if previous is None or previous.payload.get("inputFingerprint") != input_fp:
        return []
    avoided = {item.strip().casefold() for item in avoid}
    return [
        flag for flag in _flags_from(previous.payload) if flag.item.strip().casefold() in avoided
    ]


def refresh_hidden_ingredients(
    session_factory: sessionmaker[Session],
    recipe_id: UUID,
    *,
    decisions: DecisionAsker | None = None,
) -> str:
    """Bring a recipe's stored check up to date; returns the resulting status.

    Idempotent: a stored result with a matching fingerprint is left alone.
    """

    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None:
            return NOT_CHECKED
        avoid = owner_avoid_list(session)
        config = decisions_config(load_config(session))
        models = config.feature(Purpose.HIDDEN_INGREDIENTS).models
        current = fingerprint(recipe, avoid, models)
        input_fp = input_fingerprint(recipe, models)
        stored = _stored(session, recipe_id)
        if stored is not None and stored.fingerprint == current and stored.status == CHECKED:
            return CHECKED
        carried = _still_valid(stored, input_fp, avoid)
        if not avoid:
            result = HiddenCheck(NO_LIST, ())
        else:
            engine = decisions or build_decisions(session_factory, config)
            active = getattr(engine, "active", None)
            if callable(active) and not active(Purpose.HIDDEN_INGREDIENTS):
                result = HiddenCheck(NOT_CHECKED, ())
            else:
                named = ingredient_warnings(recipe.ingredients, avoid)
                result = check_hidden(
                    engine,
                    recipe_title=recipe.title,
                    lines=[HiddenLine(item.id, item.original_text) for item in recipe.ingredients],
                    avoid=avoid,
                    already=frozenset((w.ingredient_id, w.item) for w in named),
                )
    with session_factory.begin() as session:
        row = _stored(session, recipe_id)
        if row is None:
            row = RecipeInsight(recipe_id=recipe_id, kind=KIND)
            session.add(row)
        flags = list(result.flags)
        if result.status != CHECKED:
            # A check that could not finish keeps the warnings that are still valid.
            seen = {(flag.ingredient_id, flag.item.casefold()) for flag in flags}
            flags += [f for f in carried if (f.ingredient_id, f.item.casefold()) not in seen]
        row.fingerprint = current
        row.status = result.status
        row.payload = {
            "inputFingerprint": input_fp,
            "flags": [
                {
                    "ingredientId": str(flag.ingredient_id),
                    "item": flag.item,
                    "probability": str(flag.probability),
                }
                for flag in flags
            ],
        }
    logger.info("Hidden-ingredient check for a recipe finished: %s.", result.status)
    return result.status


def stored_hidden(
    session: Session, recipe: Recipe, avoid: Sequence[str]
) -> tuple[str, tuple[AvoidWarning, ...]]:
    """The stored status and model warnings, or "not checked" when missing or out of date."""

    if not avoid:
        return NO_LIST, ()
    models = decisions_config(load_config(session)).feature(Purpose.HIDDEN_INGREDIENTS).models
    row = _stored(session, recipe.id)
    if row is None:
        return NOT_CHECKED, ()
    if row.fingerprint == fingerprint(recipe, avoid, models):
        return row.status, tuple(_flags_from(row.payload))
    # Out of date: not checked, but warnings that still apply stay visible.
    return NOT_CHECKED, tuple(_still_valid(row, input_fingerprint(recipe, models), avoid))


def refresh_all_hidden_ingredients(session_factory: sessionmaker[Session]) -> int:
    """Recheck every recipe (after the avoid list or models change); returns how many ran."""

    with session_factory() as session:
        recipe_ids = list(session.scalars(select(Recipe.id)))
    decisions = build_decisions(session_factory)
    for recipe_id in recipe_ids:
        try:
            refresh_hidden_ingredients(session_factory, recipe_id, decisions=decisions)
        except Exception:
            logger.exception("Hidden-ingredient check failed for a recipe.")
    return len(recipe_ids)


def _stored(session: Session, recipe_id: UUID) -> RecipeInsight | None:
    return session.scalar(
        select(RecipeInsight).where(
            RecipeInsight.recipe_id == recipe_id, RecipeInsight.kind == KIND
        )
    )
