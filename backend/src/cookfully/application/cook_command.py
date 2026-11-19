"""Interpret a spoken or typed cook-mode command with the decision panel.

The panel chooses an intent from ``domain.cook_command.INTENTS``. A timer's length is read from the
words by rule. The answer carries the probabilities of the leading intents: the client acts at once
when the top one is clear and otherwise asks "did you mean ...?", so a mis-hearing costs one tap.
Actions here only move through steps or start a timer, all trivially undone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import build_decisions
from cookfully.domain.common import DomainError
from cookfully.domain.cook_command import INTENTS, clean, spoken_minutes
from cookfully.domain.decisions import Ask, Choice, DecisionAsker, Purpose
from cookfully.infrastructure.models.recipes import Recipe

ACT_AT = Decimal(
    "0.6"
)  # measured: no wrong action at 0.6, one at 0.5 (docs/decision-model-experiments)
MAX_ALTERNATIVES = 3
INSTRUCTIONS = (
    "What does the cook want the cooking app to do? The utterance may be a speech-to-text "
    "transcript, so allow for mishearing. If it is not clearly an instruction to the app, "
    "choose none."
)


@dataclass(frozen=True, slots=True)
class Alternative:
    intent: str
    probability: Decimal


@dataclass(frozen=True, slots=True)
class CookCommand:
    intent: str  # one of INTENTS; "none" when nothing usable
    probability: Decimal | None
    minutes: int | None  # for "timer", read from the words
    act: bool  # True: do it now. False: ask the cook to confirm one of `alternatives`
    alternatives: tuple[Alternative, ...]


def interpret(
    decisions: DecisionAsker, utterance: str, *, step: str, step_number: int, total_steps: int
) -> CookCommand:
    text = clean(utterance)
    if not text:
        return CookCommand("none", None, None, False, ())
    [answers] = decisions.ask(
        [
            Ask(
                Purpose.COOK_COMMAND,
                {
                    "utterance": text,
                    "step": " ".join(step.split())[:400],
                    "position": f"step {step_number} of {total_steps}",
                },
                {"intent": Choice(INSTRUCTIONS, INTENTS)},
            )
        ]
    )
    probabilities = answers.choice("intent")
    if not probabilities:
        return CookCommand("none", None, None, False, ())
    ranked = sorted(
        ((key, value) for key, value in probabilities.items() if key in INTENTS),
        key=lambda item: (-item[1], item[0]),
    )
    if not ranked:
        return CookCommand("none", None, None, False, ())
    top, probability = ranked[0]
    alternatives = tuple(
        Alternative(key, value) for key, value in ranked if key != "none" and value > Decimal(0)
    )[:MAX_ALTERNATIVES]
    minutes = spoken_minutes(text) if top == "timer" else None
    if top == "none":
        return CookCommand("none", probability, None, False, alternatives)
    # a timer without a length is not actionable: ask rather than guess minutes
    act = probability >= ACT_AT and not (top == "timer" and minutes is None)
    return CookCommand(top, probability, minutes, act, alternatives)


def interpret_for_recipe(
    session_factory: sessionmaker[Session], recipe_id: UUID, utterance: str, step_index: int
) -> CookCommand:
    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None:
            raise DomainError("recipe_not_found", "Recipe was not found.", 404)
        steps = [item.text for item in recipe.instructions]
    if not 0 <= step_index < max(len(steps), 1):
        raise DomainError("step_invalid", "That step does not exist.", 422)
    step = steps[step_index] if steps else ""
    return interpret(
        build_decisions(session_factory),
        utterance,
        step=step,
        step_number=step_index + 1,
        total_steps=len(steps),
    )
