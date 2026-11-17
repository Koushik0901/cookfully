"""On-demand substitution suggestions for one ingredient of one recipe.

Candidates and amounts come from ``domain.substitutions.TABLE``. The decision panel answers, per
candidate, whether it would work in this recipe; answers are cached by the engine, so asking again
is instant and free. Without answers the table's candidates are returned unranked.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.decisions import build_decisions
from cookfully.domain.common import DomainError
from cookfully.domain.decisions import Answers, Ask, Check, Purpose
from cookfully.domain.substitutions import TABLE, RankedSubstitute, rank, table_key
from cookfully.infrastructure.models.recipes import Recipe

TEXT_LIMIT = 3000
INSTRUCTIONS = (
    "Would replacing original_line with the substitute (in the amount given) work well in this "
    "recipe, keeping the dish good to eat? Consider the cooking method and the role the "
    "ingredient plays (structure, moisture, fat, acid, flavour)."
)


class DecisionAsker(Protocol):
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...


@dataclass(frozen=True, slots=True)
class SubstitutionResult:
    ingredient_id: UUID
    original_text: str
    key: str | None
    substitutes: tuple[RankedSubstitute, ...]
    ranked: bool


def suggest(
    decisions: DecisionAsker,
    *,
    recipe_title: str,
    ingredients: Sequence[str],
    steps: Sequence[str],
    ingredient_id: UUID,
    line: str,
) -> SubstitutionResult:
    key = table_key(line)
    if key is None:
        return SubstitutionResult(ingredient_id, line, None, (), False)
    candidates = TABLE[key]
    context = {
        "recipe": recipe_title,
        "ingredients": "\n".join(ingredients)[:TEXT_LIMIT],
        "steps": "\n".join(steps)[:TEXT_LIMIT],
        "original_line": line,
    }
    asks = [
        Ask(
            Purpose.SUBSTITUTIONS,
            {**context, "substitute": f"{item.name} ({item.amount})"},
            {"works": Check(INSTRUCTIONS, "Works well here.", "Would not work well here.")},
        )
        for item in candidates
    ]
    probabilities = [answers.check("works") for answers in decisions.ask(asks)]
    ranked = rank(candidates, probabilities)
    return SubstitutionResult(
        ingredient_id, line, key, ranked, any(p is not None for p in probabilities)
    )


def suggest_for_ingredient(
    session_factory: sessionmaker[Session], recipe_id: UUID, ingredient_id: UUID
) -> SubstitutionResult:
    with session_factory() as session:
        recipe = session.get(Recipe, recipe_id)
        if recipe is None:
            raise DomainError("recipe_not_found", "Recipe was not found.", 404)
        line = next((item for item in recipe.ingredients if item.id == ingredient_id), None)
        if line is None:
            raise DomainError("ingredient_not_found", "Ingredient was not found.", 404)
        title = recipe.title
        ingredients = [item.original_text for item in recipe.ingredients]
        steps = [item.text for item in recipe.instructions]
        original = line.original_text
    return suggest(
        build_decisions(session_factory),
        recipe_title=title,
        ingredients=ingredients,
        steps=steps,
        ingredient_id=ingredient_id,
        line=original,
    )
