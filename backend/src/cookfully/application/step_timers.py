"""Timers for a recipe's steps: deterministic durations, decided by the decision panel.

Durations are read from the step text (``domain.step_timers``). For a step that has any, the panel
chooses which one is *the* timed wait (or none: "ready in 30 minutes", "makes 4 servings in 20
minutes") and says whether the cook is free while it runs. Answers are cached by step text, so a
repeat visit costs nothing. A panel that cannot answer yields no timers and cook mode keeps its
manual timer button, so the owner is always the backstop.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import build_decisions
from cookfully.domain.common import DomainError
from cookfully.domain.decisions import Answers, Ask, Check, Choice, Purpose
from cookfully.domain.step_timers import Duration, durations
from cookfully.infrastructure.models.recipes import Recipe

TEXT_LIMIT = 800
MAX_STEPS = 80
NONE = "none"
INSTRUCTIONS = (
    "Which of the listed durations is a timed wait the cook should set a kitchen timer for in "
    "this step (cooking, simmering, baking, resting, chilling)? Choose none if no listed duration "
    "is such a wait, for example a total time, a make-ahead note or a serving size."
)
PASSIVE = "Is the cook free to do other things while this runs, rather than stirring or watching?"


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


@dataclass(frozen=True, slots=True)
class StepTimer:
    step: int  # zero-based
    minutes: int
    longest_minutes: int
    text: str
    passive: bool | None  # None when the panel did not say


def timers_for_steps(decisions: DecisionAsker, steps: Sequence[str]) -> list[StepTimer]:
    candidates: list[tuple[int, str, list[Duration]]] = []
    for index, step in enumerate(steps[:MAX_STEPS]):
        text = " ".join(step.split())[:TEXT_LIMIT]
        found = durations(text)
        if found:
            candidates.append((index, text, found))
    if not candidates:
        return []
    asks = [
        Ask(
            Purpose.STEP_TIMERS,
            {"step": text, "durations": "; ".join(item.text for item in found)},
            {
                "timer": Choice(
                    INSTRUCTIONS,
                    {
                        **{
                            f"d{position}": f"{item.text}, about {item.minutes} minutes"
                            for position, item in enumerate(found)
                        },
                        NONE: "None of these is a timed wait.",
                    },
                ),
                "passive": Check(PASSIVE, "Free to do other things.", "Needs attention."),
            },
        )
        for _, text, found in candidates
    ]
    timers: list[StepTimer] = []
    for (index, _, found), answers in zip(candidates, decisions.ask(asks), strict=True):
        top = answers.top("timer")
        if top is None or top == NONE or not top.startswith("d"):
            continue
        position = int(top[1:])
        if position >= len(found):
            continue
        chosen = found[position]
        passive = answers.check("passive")
        timers.append(
            StepTimer(
                index,
                chosen.minutes,
                chosen.longest_minutes,
                chosen.text,
                None if passive is None else passive >= Decimal("0.5"),
            )
        )
    return timers


def timers_for_recipe(session_factory: sessionmaker[Session], recipe_id: UUID) -> list[StepTimer]:
    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None:
            raise DomainError("recipe_not_found", "Recipe was not found.", 404)
        steps = [item.text for item in recipe.instructions]
    return timers_for_steps(build_decisions(session_factory), steps)
