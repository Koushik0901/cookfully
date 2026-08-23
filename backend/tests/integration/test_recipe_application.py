from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.auth import AuthService
from cookfully.application.corrections import CorrectionService
from cookfully.application.recipes import IngredientWrite, RecipeService, RecipeWrite
from cookfully.domain.common import DomainError, uuid7
from cookfully.domain.ingredient_nutrition.matching import FoodMatcher
from cookfully.infrastructure.erasure_ledger import ErasureLedger
from cookfully.infrastructure.models.jobs import OutboxEvent, ProcessingJob
from cookfully.infrastructure.models.nutrition import (
    IngredientMatch,
    NutritionCorrection,
    NutritionEstimate,
)
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset
from cookfully.infrastructure.repositories.nutrition import NutritionRepository


def recipe_write(title: str = "Training bowl", servings: str = "2.000") -> RecipeWrite:
    return RecipeWrite(
        title=title,
        yield_quantity=Decimal(servings),
        ingredients=(
            IngredientWrite(
                original_text="200 g chicken breast",
                quantity_min=Decimal("200.000000"),
                quantity_max=Decimal("200.000000"),
                unit_code="gram",
                unit_text="g",
                food_name="chicken breast",
            ),
        ),
        instructions=("Cook the chicken.", "Serve."),
    )


def service(session_factory: sessionmaker[Session], tmp_path: Path) -> RecipeService:
    return RecipeService(
        session_factory,
        ErasureLedger(tmp_path / "ledger"),
        source_instance_id=uuid7(),
    )


def bootstrap_owner_id(session_factory: sessionmaker[Session]) -> UUID:
    return (
        AuthService(session_factory)
        .bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
        .id
    )


def test_recipe_create_update_archive_restore_and_delete_are_transactional(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    recipes = service(session_factory, tmp_path)
    owner_id = bootstrap_owner_id(session_factory)
    created = recipes.create(recipe_write(), trace_id="trace-create", owner_id=owner_id)
    assert created.job is not None and created.job.status == "queued"

    with session_factory() as session:
        stored = session.get(Recipe, created.recipe.id)
        assert stored is not None and stored.version == 1
        assert len(session.scalars(select(ProcessingJob)).all()) == 1
        assert len(session.scalars(select(OutboxEvent)).all()) == 1

    updated = recipes.update(
        created.recipe.id,
        recipe_write("Training bowl updated", "3.000"),
        expected_version=1,
        trace_id="trace-update",
        owner_id=owner_id,
    )
    assert updated.recipe.version == 2
    with session_factory() as session:
        jobs = list(session.scalars(select(ProcessingJob).order_by(ProcessingJob.accepted_at)))
        assert [job.status for job in jobs] == ["superseded", "queued"]

    archived = recipes.archive(created.recipe.id, expected_version=2)
    assert archived.status == "archived"
    assert archived.archived_from_status == "draft"
    with session_factory() as session:
        assert all(
            job.status == "superseded" for job in session.scalars(select(ProcessingJob)).all()
        )

    restored = recipes.restore(created.recipe.id, expected_version=3)
    assert restored.status == "draft"
    assert restored.nutrition_state == "stale"
    recipes.archive(created.recipe.id, expected_version=4)
    record = recipes.permanent_delete(
        created.recipe.id,
        confirmed=True,
        latest_backup_expiry=datetime.now(UTC) + timedelta(days=7),
    )
    assert record.subject_id == created.recipe.id
    assert record.scope == "recipe_owned"
    with session_factory() as session:
        assert session.get(Recipe, created.recipe.id) is None
    assert ErasureLedger(tmp_path / "ledger").verify() == [record]


def test_recipe_write_and_job_outbox_roll_back_together(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch
) -> None:
    recipes = service(session_factory, tmp_path)
    owner_id = bootstrap_owner_id(session_factory)

    def fail_acceptance(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(recipes._jobs, "accept_in_session", fail_acceptance)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        recipes.create(recipe_write(), trace_id="trace-rollback", owner_id=owner_id)
    with session_factory() as session:
        assert session.scalar(select(Recipe)) is None
        assert session.scalar(select(ProcessingJob)) is None
        assert session.scalar(select(OutboxEvent)) is None


def test_typed_corrections_quantize_supersede_and_retain_reset_audit(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    recipe = (
        service(session_factory, tmp_path)
        .create(recipe_write(), trace_id="trace-corrections", owner_id=owner.id)
        .recipe
    )
    corrections = CorrectionService(session_factory)

    first = corrections.activate(
        recipe_id=recipe.id,
        ingredient_id=None,
        field="calories_kcal",
        decimal_value=Decimal("123.4567895"),
        created_by=owner.id,
        reason="Measured serving",
    )
    assert first.decimal_value == Decimal("123.456790")
    second = corrections.activate(
        recipe_id=recipe.id,
        ingredient_id=None,
        field="calories_kcal",
        decimal_value=Decimal("125"),
        created_by=owner.id,
    )
    with session_factory() as session:
        audit = list(
            session.scalars(select(NutritionCorrection).order_by(NutritionCorrection.created_at))
        )
        assert len(audit) == 2
        assert [item.active for item in audit] == [False, True]

    corrections.reset(second.id)
    with session_factory() as session:
        reset = session.get(NutritionCorrection, second.id)
        assert reset is not None and reset.active is False and reset.reset_at is not None
        assert len(session.scalars(select(NutritionCorrection)).all()) == 2

    with pytest.raises(DomainError, match="exactly one"):
        corrections.activate(
            recipe_id=recipe.id,
            ingredient_id=None,
            field="fat_g",
            decimal_value=Decimal("1"),
            text_value="one",
            created_by=owner.id,
        )
    with pytest.raises(DomainError, match="out of range"):
        corrections.activate(
            recipe_id=recipe.id,
            ingredient_id=None,
            field="yield_quantity",
            decimal_value=Decimal("0"),
            created_by=owner.id,
        )


def test_nutrition_repository_search_match_and_estimate_activation(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    owner_id = bootstrap_owner_id(session_factory)
    recipe = (
        service(session_factory, tmp_path)
        .create(recipe_write(), trace_id="trace-nutrition-repository", owner_id=owner_id)
        .recipe
    )
    with session_factory.begin() as session:
        dataset = ReferenceDataset(
            id=uuid7(),
            provider="usda_fdc",
            dataset_type="foundation",
            release_id="foundation-2026-04",
            released_on=datetime(2026, 4, 1, tzinfo=UTC).date(),
            imported_at=datetime.now(UTC),
            source_url="https://fdc.nal.usda.gov/",
            license="CC0-1.0",
            status="active",
            checked_at=datetime.now(UTC),
            activated_at=datetime.now(UTC),
        )
        food = FoodReference(
            id=uuid7(),
            dataset=dataset,
            external_id="1001",
            description="Chicken breast",
            normalized_name="chicken breast",
            data_type="foundation",
            basis_grams=Decimal("100.000000"),
        )
        session.add(dataset)
        session.add(food)

    with session_factory.begin() as session:
        stored_recipe = session.get(Recipe, recipe.id)
        assert stored_recipe is not None
        ingredient = stored_recipe.ingredients[0]
        repository = NutritionRepository(session)
        matcher = FoodMatcher(repository)
        decision = matcher.decide("chicken breast")
        assert decision.status == "matched" and decision.candidate is not None
        match = matcher.activate_manual(
            ingredient.id,
            decision.candidate.food,
            input_hash=stored_recipe.input_hash,
            grams_min=Decimal("200.000000"),
        )
        assert match.source_release_id == "foundation-2026-04"
        assert repository.active_match(ingredient.id).id == match.id  # type: ignore[union-attr]

        estimate = NutritionEstimate(
            recipe_id=stored_recipe.id,
            status="estimated",
            basis_servings=Decimal("2.000"),
            calories_kcal=Decimal("300.000000"),
            protein_g=Decimal("40.000000"),
            carbohydrate_g=Decimal("10.000000"),
            fat_g=Decimal("8.000000"),
            coverage_ratio=Decimal("1.000000"),
            source_label="USDA FoodData Central",
            input_hash=stored_recipe.input_hash,
            pipeline_version="nutrition-v1",
            calculated_at=datetime.now(UTC),
        )
        repository.activate_estimate(stored_recipe, estimate)
        assert stored_recipe.active_estimate_id == estimate.id
        assert stored_recipe.status == "ready"

        with pytest.raises(DomainError, match="changed"):
            repository.activate_estimate(
                stored_recipe,
                NutritionEstimate(
                    recipe_id=stored_recipe.id,
                    status="estimated",
                    basis_servings=Decimal("2.000"),
                    coverage_ratio=Decimal("1.000000"),
                    input_hash="sha256:stale",
                    pipeline_version="nutrition-v2",
                    calculated_at=datetime.now(UTC),
                ),
            )

    with session_factory() as session:
        assert len(session.scalars(select(IngredientMatch)).all()) == 1
