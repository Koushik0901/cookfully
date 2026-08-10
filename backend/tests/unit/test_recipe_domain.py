from decimal import Decimal
from uuid import UUID

import pytest

from vigor_vine.domain.common import DomainError
from vigor_vine.domain.recipes import IngredientInput, RecipeDraft, RecipeLifecycle


def sample_recipe() -> RecipeDraft:
    return RecipeDraft(
        id=UUID("0198a9f0-dddd-7ddd-8ddd-dddddddddddd"),
        title="Training bowl",
        yield_quantity=Decimal("2.000"),
        ingredients=(IngredientInput("200 g chicken", Decimal("200"), "gram", "chicken"),),
        instructions=("Cook the chicken.",),
        status="ready",
        nutrition_state="estimated",
    )


def test_archive_restore_and_stale_input_lifecycle() -> None:
    recipe = sample_recipe()
    original_hash = recipe.input_hash()
    lifecycle = RecipeLifecycle(recipe)
    lifecycle.archive()
    assert recipe.status == "archived" and recipe.archived_from_status == "ready"
    lifecycle.restore(current_estimate_input_hash=original_hash)
    assert recipe.status == "ready" and recipe.nutrition_state == "estimated"

    lifecycle.archive()
    recipe.yield_quantity = Decimal("3.000")
    lifecycle.restore(current_estimate_input_hash=original_hash)
    assert recipe.status == "ready" and recipe.nutrition_state == "stale"


def test_permanent_delete_requires_archived_confirmation_and_detaches_history() -> None:
    recipe = sample_recipe()
    lifecycle = RecipeLifecycle(recipe)
    with pytest.raises(DomainError, match="archived"):
        lifecycle.permanent_delete(confirmed=True, historical_titles=["Training bowl"])
    lifecycle.archive()
    with pytest.raises(DomainError, match="confirmation"):
        lifecycle.permanent_delete(confirmed=False, historical_titles=["Training bowl"])
    result = lifecycle.permanent_delete(confirmed=True, historical_titles=["Training bowl"])
    assert result.recipe_id == recipe.id
    assert result.detached_historical_titles == ("Training bowl",)
    assert result.supersede_active_jobs is True


def test_processing_recipe_archives_to_a_safe_prior_state_and_hash_is_deterministic() -> None:
    recipe = sample_recipe()
    assert recipe.input_hash() == sample_recipe().input_hash()
    recipe.ingredients = (IngredientInput("200 g chicken", Decimal("201"), "gram", "chicken"),)
    assert recipe.input_hash() != sample_recipe().input_hash()
    recipe.status = "processing"
    recipe.nutrition_state = "pending"
    RecipeLifecycle(recipe).archive()
    assert recipe.status == "archived"
    assert recipe.archived_from_status == "draft"

    with pytest.raises(DomainError, match="cannot be archived"):
        RecipeLifecycle(recipe).archive()
