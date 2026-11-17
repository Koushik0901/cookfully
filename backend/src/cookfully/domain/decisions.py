"""Typed questions for decision models, and how answers from a panel of models are combined.

A decision model reads a short ``state`` and typed questions, and returns probabilities: ``Choice``
(which option), ``Check`` (does this hold) and ``Score`` (where on an ordered scale). The engine in
``application.decisions`` sends an ``Ask`` to every model on a feature's panel; this module holds
the request types, the validation of what came back, and the aggregation rules features rely on.

Pure: no I/O, decimals only.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum

_ZERO = Decimal(0)
_ONE = Decimal(1)


class Purpose(StrEnum):
    """One value per feature. Selects settings and the model panel, and namespaces the cache."""

    MATCH_REFEREE = "match_referee"
    FOOD_LABELS = "food_labels"
    IMPORT_LINE_GATE = "import_line_gate"
    IMPORT_SCREEN = "import_screen"
    CLEANUP_VERIFIER = "cleanup_verifier"
    HIDDEN_INGREDIENTS = "hidden_ingredients"
    RECIPE_FACETS = "recipe_facets"
    SUBSTITUTIONS = "substitutions"
    GROCERY_TIDY = "grocery_tidy"
    SHELF_LIFE = "shelf_life"


@dataclass(frozen=True, slots=True)
class Choice:
    """Which of these options. Keys are the caller's; descriptions are what the model reads."""

    instructions: str
    options: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Check:
    """Does this hold. The answer is P(yes)."""

    instructions: str
    yes: str
    no: str


@dataclass(frozen=True, slots=True)
class Score:
    """Where on an ordered scale, listed low to high. The answer is normalized to [0, 1]."""

    instructions: str
    levels: Sequence[str]


Question = Choice | Check | Score


@dataclass(frozen=True, slots=True)
class Ask:
    """One request. ``state`` values are data for the model to read, never instructions."""

    purpose: Purpose
    state: Mapping[str, str]
    questions: Mapping[str, Question]


@dataclass(frozen=True, slots=True)
class ModelAnswers:
    """What one model answered. A question missing here was not answered usably."""

    choices: Mapping[str, Mapping[str, Decimal]] = field(default_factory=dict)
    checks: Mapping[str, Decimal] = field(default_factory=dict)
    scores: Mapping[str, Decimal] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        return {
            "choices": {
                name: {key: str(value) for key, value in probabilities.items()}
                for name, probabilities in self.choices.items()
            },
            "checks": {name: str(value) for name, value in self.checks.items()},
            "scores": {name: str(value) for name, value in self.scores.items()},
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, object]) -> ModelAnswers | None:
        try:
            choices = payload.get("choices") or {}
            checks = payload.get("checks") or {}
            scores = payload.get("scores") or {}
            if not isinstance(choices, dict) or not isinstance(checks, dict):
                return None
            if not isinstance(scores, dict):
                return None
            return cls(
                {
                    str(name): {str(key): Decimal(str(value)) for key, value in probs.items()}
                    for name, probs in choices.items()
                },
                {str(name): Decimal(str(value)) for name, value in checks.items()},
                {str(name): Decimal(str(value)) for name, value in scores.items()},
            )
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            return None


@dataclass(frozen=True, slots=True)
class Answers:
    """Answers from every model on the panel that answered. Empty means no opinion."""

    by_model: Mapping[str, ModelAnswers] = field(default_factory=dict)
    # Models the panel asked; ``complete`` is False when some of them did not answer.
    asked: int = 0

    @property
    def complete(self) -> bool:
        return bool(self.by_model) and len(self.by_model) >= self.asked

    def __bool__(self) -> bool:
        return bool(self.by_model)

    def choice(self, name: str) -> dict[str, Decimal] | None:
        """Mean probability per option over the models that answered, renormalized."""

        answered = [item.choices[name] for item in self.by_model.values() if name in item.choices]
        if not answered:
            return None
        keys = {key for probabilities in answered for key in probabilities}
        mean = {
            key: sum((probs.get(key, _ZERO) for probs in answered), _ZERO) / len(answered)
            for key in keys
        }
        total = sum(mean.values(), _ZERO)
        if total <= _ZERO:
            return None
        return {key: value / total for key, value in mean.items()}

    def top(self, name: str) -> str | None:
        """The option with the highest mean probability (ties broken by key)."""

        probabilities = self.choice(name)
        if not probabilities:
            return None
        return max(sorted(probabilities), key=lambda key: probabilities[key])

    def agree(self, name: str) -> bool:
        """True when every model that answered picked the same top option."""

        tops = {
            max(sorted(item.choices[name]), key=lambda key: item.choices[name][key])
            for item in self.by_model.values()
            if item.choices.get(name)
        }
        return len(tops) == 1

    def check(self, name: str) -> Decimal | None:
        """Mean P(yes) over the models that answered."""

        values = [item.checks[name] for item in self.by_model.values() if name in item.checks]
        return sum(values, _ZERO) / len(values) if values else None

    def check_worst(self, name: str) -> Decimal | None:
        """Highest P(yes) over the models that answered: for fail-closed safety checks."""

        values = [item.checks[name] for item in self.by_model.values() if name in item.checks]
        return max(values) if values else None

    def check_least(self, name: str) -> Decimal | None:
        """Lowest P(yes) over the models that answered: for claims every model must back."""

        values = [item.checks[name] for item in self.by_model.values() if name in item.checks]
        return min(values) if values else None

    def score(self, name: str) -> Decimal | None:
        """Mean normalized score in [0, 1] over the models that answered."""

        values = [item.scores[name] for item in self.by_model.values() if name in item.scores]
        return sum(values, _ZERO) / len(values) if values else None


def request_hash(model: str, ask: Ask) -> str:
    """Stable cache key. Any change to purpose, state or wording gives a new key."""

    blob = json.dumps(
        [model, ask.purpose.value, dict(ask.state), _questions_json(ask.questions)],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _questions_json(questions: Mapping[str, Question]) -> dict[str, object]:
    encoded: dict[str, object] = {}
    for name, question in questions.items():
        if isinstance(question, Choice):
            encoded[name] = ["choice", question.instructions, dict(question.options)]
        elif isinstance(question, Check):
            encoded[name] = ["check", question.instructions, question.yes, question.no]
        else:
            encoded[name] = ["score", question.instructions, list(question.levels)]
    return encoded


def wire_questions(ask: Ask, *, shuffle_seed: str) -> dict[str, dict[str, object]]:
    """The ``questions`` body for the Decisions API.

    Choice options are reordered by a hash of ``shuffle_seed`` and the key, so option position
    carries no systematic bias across requests while staying reproducible. Score levels keep their
    order because the scale is ordered.
    """

    body: dict[str, dict[str, object]] = {}
    for name, question in ask.questions.items():
        if isinstance(question, Choice):
            order = sorted(
                question.options,
                key=lambda key: hashlib.sha256(f"{shuffle_seed}:{key}".encode()).hexdigest(),
            )
            body[name] = {
                "type": "choice",
                "instructions": question.instructions,
                "criteria": {key: question.options[key] for key in order},
            }
        elif isinstance(question, Check):
            body[name] = {
                "type": "noul",
                "instructions": question.instructions,
                "criteria": {"true": question.yes, "false": question.no},
            }
        else:
            body[name] = {
                "type": "score",
                "instructions": question.instructions,
                "criteria": list(question.levels),
            }
    return body


def parse_answers(ask: Ask, raw: object) -> ModelAnswers | None:
    """Validate a model's raw ``answers`` object against the questions asked.

    A malformed value (non-numeric, NaN, outside [0, 1]) rejects the model's whole answer, since it
    signals a broken response. A question that is simply missing is left out.
    """

    if not isinstance(raw, Mapping):
        return None
    choices: dict[str, dict[str, Decimal]] = {}
    checks: dict[str, Decimal] = {}
    scores: dict[str, Decimal] = {}
    for name, question in ask.questions.items():
        answer = raw.get(name)
        if not isinstance(answer, Mapping):
            continue
        if isinstance(question, Choice):
            parsed = _parse_choice(answer, question)
            if parsed is None:
                return None
            if parsed:
                choices[name] = parsed
        elif isinstance(question, Check):
            if answer.get("type") != "noul":
                continue
            value = _probability(answer.get("noul"))
            if value is None:
                return None
            checks[name] = value
        else:
            if answer.get("type") != "score":
                continue
            level = _decimal(answer.get("score"))
            top = Decimal(len(question.levels) - 1)
            if level is None or top <= _ZERO or level < _ZERO or level > top:
                return None
            scores[name] = level / top
    return ModelAnswers(choices, checks, scores)


def _parse_choice(answer: Mapping[str, object], question: Choice) -> dict[str, Decimal] | None:
    """Probabilities over the asked options; ``None`` when malformed, ``{}`` when absent."""

    if answer.get("type") != "choice":
        return {}
    raw = answer.get("probabilities")
    pairs: list[tuple[str, object]]
    if isinstance(raw, Mapping) and raw:
        pairs = [(str(key), value) for key, value in raw.items()]
    elif isinstance(answer.get("choice"), str):
        pairs = [(str(answer["choice"]), answer.get("confidence", 1))]
    else:
        return {}
    kept: dict[str, Decimal] = {}
    for key, value in pairs:
        probability = _probability(value)
        if probability is None:
            return None
        if key in question.options:
            kept[key] = probability
    total = sum(kept.values(), _ZERO)
    if total <= _ZERO:
        return {}
    return {key: value / total for key, value in kept.items()}


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _probability(value: object) -> Decimal | None:
    number = _decimal(value)
    if number is None or number < _ZERO or number > _ONE:
        return None
    return number
