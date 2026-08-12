from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from uuid import UUID

from cookfully.domain.common import DomainError, canonical_decimal

RecipeStatus = Literal["draft", "processing", "ready", "partial", "failed", "archived"]
NutritionState = Literal["pending", "source_provided", "estimated", "partial", "failed", "stale"]


@dataclass(frozen=True, slots=True)
class IngredientInput:
    original_text: str
    quantity: Decimal | None = None
    unit_code: str | None = None
    food_name: str | None = None
    optional: bool = False


@dataclass(slots=True)
class RecipeDraft:
    id: UUID
    title: str
    yield_quantity: Decimal
    ingredients: tuple[IngredientInput, ...]
    instructions: tuple[str, ...]
    status: RecipeStatus = "draft"
    nutrition_state: NutritionState = "pending"
    archived_from_status: RecipeStatus | None = None

    def input_hash(self) -> str:
        payload = {
            "title": self.title.strip(),
            "yield": canonical_decimal(self.yield_quantity, places=3),
            "ingredients": [
                {
                    "original": item.original_text,
                    "quantity": (
                        canonical_decimal(item.quantity) if item.quantity is not None else None
                    ),
                    "unit": item.unit_code,
                    "food": item.food_name,
                    "optional": item.optional,
                }
                for item in self.ingredients
            ],
            "instructions": list(self.instructions),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True, slots=True)
class PermanentDeletion:
    recipe_id: UUID
    detached_historical_titles: tuple[str, ...]
    supersede_active_jobs: bool


class RecipeLifecycle:
    def __init__(self, recipe: RecipeDraft) -> None:
        self.recipe = recipe

    def archive(self) -> None:
        if self.recipe.status not in {"draft", "processing", "ready", "partial", "failed"}:
            raise DomainError("invalid_archive_state", "This recipe cannot be archived now.", 409)
        prior_status = self.recipe.status
        if prior_status == "processing":
            if self.recipe.nutrition_state == "partial":
                prior_status = "partial"
            elif self.recipe.nutrition_state in {"source_provided", "estimated"}:
                prior_status = "ready"
            else:
                prior_status = "draft"
        self.recipe.archived_from_status = prior_status
        self.recipe.status = "archived"

    def restore(self, *, current_estimate_input_hash: str | None) -> None:
        if self.recipe.status != "archived" or self.recipe.archived_from_status is None:
            raise DomainError(
                "invalid_restore_state", "Only an archived recipe can be restored.", 409
            )
        self.recipe.status = self.recipe.archived_from_status
        self.recipe.archived_from_status = None
        if current_estimate_input_hash != self.recipe.input_hash():
            self.recipe.nutrition_state = "stale"

    def permanent_delete(
        self,
        *,
        confirmed: bool,
        historical_titles: list[str],
    ) -> PermanentDeletion:
        if self.recipe.status != "archived":
            raise DomainError(
                "archive_required", "The recipe must be archived before permanent deletion.", 409
            )
        if not confirmed:
            raise DomainError(
                "confirmation_required", "Permanent deletion requires confirmation.", 422
            )
        return PermanentDeletion(self.recipe.id, tuple(historical_titles), True)
