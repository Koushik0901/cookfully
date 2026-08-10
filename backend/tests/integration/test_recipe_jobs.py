from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.application.auth import AuthService
from vigor_vine.application.corrections import CorrectionService
from vigor_vine.application.jobs import JobService
from vigor_vine.application.recipes import IngredientWrite, RecipeService, RecipeWrite
from vigor_vine.domain.common import DomainError, uuid7
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.models.jobs import OutboxEvent, ProcessingJob
from vigor_vine.infrastructure.models.media import MediaAsset
from vigor_vine.infrastructure.models.nutrition import NutritionCorrection, NutritionEstimate
from vigor_vine.infrastructure.models.recipes import Recipe
from vigor_vine.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
    ReferenceDataset,
)
from vigor_vine.infrastructure.recipe_importer import ImportedRecipe, RecipeImporter
from vigor_vine.infrastructure.safe_fetch import SafeFetcher
from vigor_vine.jobs.recipe_pipeline import JobEnvelope, RecipePipeline
from vigor_vine.jobs.retention import sweep_retention


class ImporterStub:
    def __init__(self, result: ImportedRecipe | DomainError) -> None:
        self.result = result
        self.calls = 0

    async def import_url(self, url: str) -> ImportedRecipe:
        del url
        self.calls += 1
        if isinstance(self.result, DomainError):
            raise self.result
        return self.result


class ImageServiceStub:
    async def capture(self, url: str):
        raise DomainError("image_invalid", f"Image unavailable: {url}", 422)


async def public_resolver(_: str) -> set[str]:
    return {"93.184.216.34"}


def write() -> RecipeWrite:
    return RecipeWrite(
        title="Chicken bowl",
        yield_quantity=Decimal("2.000"),
        ingredients=(
            IngredientWrite(
                original_text="200 g chicken breast",
                quantity_min=Decimal("200.000000"),
                quantity_max=Decimal("200.000000"),
                unit_code="gram",
                food_name="chicken breast",
            ),
        ),
        instructions=("Cook.",),
    )


def recipe_service(session_factory: sessionmaker[Session], tmp_path: Path) -> RecipeService:
    return RecipeService(
        session_factory,
        ErasureLedger(tmp_path / "ledger"),
        source_instance_id=uuid7(),
    )


def envelope_for(session_factory: sessionmaker[Session], job_id: UUID) -> JobEnvelope:
    with session_factory() as session:
        job = session.get(ProcessingJob, job_id)
        assert job is not None
        return JobEnvelope(
            schema_version=1,
            job_id=job.id,
            kind=job.kind,
            aggregate_type=job.aggregate_type,
            aggregate_id=job.aggregate_id,
            input_hash=job.input_hash,
            trace_id=job.trace_id,
            requested_at=job.accepted_at,
        )


def install_reference_data(session_factory: sessionmaker[Session]) -> None:
    now = datetime.now(UTC)
    with session_factory.begin() as session:
        foundation = ReferenceDataset(
            id=uuid7(),
            provider="usda_fdc",
            dataset_type="foundation",
            release_id="foundation-2026-04",
            released_on=date(2026, 4, 1),
            imported_at=now,
            source_url="https://fdc.nal.usda.gov/",
            license="CC0-1.0",
            status="active",
            checked_at=now,
            activated_at=now,
        )
        legacy = ReferenceDataset(
            id=uuid7(),
            provider="usda_fdc",
            dataset_type="sr_legacy",
            release_id="sr-legacy-2018-04",
            released_on=date(2018, 4, 1),
            imported_at=now,
            source_url="https://fdc.nal.usda.gov/",
            license="CC0-1.0",
            status="active",
            checked_at=now,
            activated_at=now,
        )
        food = FoodReference(
            id=uuid7(),
            dataset=foundation,
            external_id="1001",
            description="Chicken breast",
            normalized_name="chicken breast",
            data_type="foundation",
            basis_grams=Decimal("100.000000"),
            nutrients=[
                FoodNutrient(nutrient_code="1008", amount=Decimal("165"), unit="kcal"),
                FoodNutrient(nutrient_code="1003", amount=Decimal("31"), unit="g"),
                FoodNutrient(nutrient_code="1005", amount=Decimal("0"), unit="g"),
                FoodNutrient(nutrient_code="1004", amount=Decimal("3.6"), unit="g"),
            ],
        )
        session.add_all([foundation, legacy, food])


def pipeline(session_factory: sessionmaker[Session], importer: ImporterStub) -> RecipePipeline:
    return RecipePipeline(
        session_factory,
        importer,  # type: ignore[arg-type]
        ImageServiceStub(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_parse_match_rollup_chain_is_idempotent_and_preserves_corrections(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    install_reference_data(session_factory)
    owner = AuthService(session_factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    started = perf_counter()
    mutation = recipe_service(session_factory, tmp_path).create(write(), trace_id="trace-chain")
    assert perf_counter() - started < 1
    assert mutation.job is not None
    correction = CorrectionService(session_factory).activate(
        recipe_id=mutation.recipe.id,
        ingredient_id=None,
        field="calories_kcal",
        decimal_value=Decimal("170"),
        created_by=owner.id,
    )
    worker = pipeline(
        session_factory,
        ImporterStub(
            DomainError("unexpected_import", "Import should not run for a manual recipe.", 500)
        ),
    )

    parsed = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert parsed.status == "succeeded" and parsed.next_job_id is not None
    matched = await worker.process(envelope_for(session_factory, parsed.next_job_id))
    assert matched.status == "succeeded" and matched.next_job_id is not None
    rolled_up = await worker.process(envelope_for(session_factory, matched.next_job_id))
    assert rolled_up.status == "succeeded" and rolled_up.next_job_id is None

    duplicate = await worker.process(envelope_for(session_factory, matched.next_job_id))
    assert duplicate.status == "succeeded"
    with session_factory() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        assert recipe is not None and recipe.status == "ready"
        estimate = session.get(NutritionEstimate, recipe.active_estimate_id)
        assert estimate is not None
        assert estimate.status == "estimated"
        assert estimate.coverage_ratio == Decimal("1.000000")
        assert estimate.calories_kcal == Decimal("165.000000")
        assert estimate.protein_g == Decimal("31.000000")
        assert estimate.carbohydrate_g == Decimal("0.000000")
        assert estimate.fat_g == Decimal("3.600000")
        active_correction = session.get(NutritionCorrection, correction.id)
        assert active_correction is not None and active_correction.active is True
        assert len(session.scalars(select(NutritionEstimate)).all()) == 1


@pytest.mark.asyncio
async def test_import_persists_source_result_and_chains_with_the_new_input_hash(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    mutation = recipe_service(session_factory, tmp_path).create_import_placeholder(
        "https://example.com/chicken", trace_id="trace-import"
    )
    assert mutation.job is not None
    importer = ImporterStub(
        ImportedRecipe(
            title="Imported chicken",
            source_url="https://example.com/chicken",
            canonical_url="https://example.com/chicken",
            image_url=None,
            yield_quantity=Decimal("2.000"),
            yield_text="2 servings",
            ingredients=("200 g chicken breast",),
            instructions=("Cook.",),
            source_nutrition={
                "calories": "165 kcal",
                "proteinContent": "31 g",
                "carbohydrateContent": "0 g",
                "fatContent": "3.6 g",
            },
        )
    )
    worker = pipeline(session_factory, importer)
    result = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert result.status == "succeeded" and result.next_job_id is not None
    assert importer.calls == 1
    with session_factory() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        next_job = session.get(ProcessingJob, result.next_job_id)
        assert recipe is not None and next_job is not None
        assert recipe.title == "Imported chicken"
        assert len(recipe.ingredients) == 1 and len(recipe.instructions) == 1
        assert next_job.kind == "ingredient_parse"
        assert next_job.input_hash == recipe.input_hash
        source = session.get(NutritionEstimate, recipe.active_estimate_id)
        assert source is not None and source.status == "source_provided"
        assert source.calories_kcal == Decimal("165.000000")


@pytest.mark.asyncio
async def test_input_change_and_archive_supersede_queued_work(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    recipes = recipe_service(session_factory, tmp_path)
    changed = recipes.create(write(), trace_id="trace-changed")
    assert changed.job is not None
    with session_factory.begin() as session:
        stored = session.get(Recipe, changed.recipe.id)
        assert stored is not None
        stored.input_hash = "sha256:changed-after-acceptance"
    worker = pipeline(
        session_factory,
        ImporterStub(DomainError("not_used", "Not used.", 500)),
    )
    stale = await worker.process(envelope_for(session_factory, changed.job.id))
    assert stale.status == "superseded"

    archived = recipes.create(write(), trace_id="trace-archive")
    assert archived.job is not None
    recipes.archive(archived.recipe.id, expected_version=1)
    result = await worker.process(envelope_for(session_factory, archived.job.id))
    assert result.status == "superseded"


@pytest.mark.asyncio
async def test_missing_reference_data_finishes_partial_without_blocking_manual_use(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    mutation = recipe_service(session_factory, tmp_path).create(write(), trace_id="trace-degraded")
    assert mutation.job is not None
    worker = pipeline(
        session_factory,
        ImporterStub(DomainError("not_used", "Not used.", 500)),
    )
    parsed = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert parsed.next_job_id is not None
    failed = await worker.process(envelope_for(session_factory, parsed.next_job_id))
    assert failed.status == "failed"
    with session_factory() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        job = session.get(ProcessingJob, parsed.next_job_id)
        assert recipe is not None and recipe.status == "partial"
        assert recipe.nutrition_state == "partial"
        assert job is not None and job.failure_code == "reference_data_unavailable"
        assert recipe.title == "Chicken bowl"


@pytest.mark.asyncio
async def test_retryable_import_failure_uses_authoritative_fixed_schedule_and_outbox(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    mutation = recipe_service(session_factory, tmp_path).create_import_placeholder(
        "https://example.com/temporary", trace_id="trace-retry"
    )
    assert mutation.job is not None
    worker = pipeline(
        session_factory,
        ImporterStub(DomainError("source_unavailable", "Source unavailable.", 422)),
    )
    result = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert result.status == "retry_wait"
    with session_factory() as session:
        job = session.get(ProcessingJob, mutation.job.id)
        assert job is not None and job.next_retry_at is not None
        assert job.max_attempts == 5
        assert (job.terminal_deadline_at - job.accepted_at).total_seconds() == 900
        elapsed_from_start = (job.next_retry_at - job.started_at).total_seconds()  # type: ignore[operator]
        assert 5 <= elapsed_from_start < 6
        retry_at = job.next_retry_at

    assert JobService(session_factory).release_due_retries(now=retry_at) == [mutation.job.id]
    with session_factory() as session:
        job = session.get(ProcessingJob, mutation.job.id)
        events = list(
            session.scalars(select(OutboxEvent).where(OutboxEvent.aggregate_id == mutation.job.id))
        )
        assert job is not None and job.status == "queued"
        assert len(events) == 2 and events[-1].event_type == "processing_job.retry_due.v1"


@pytest.mark.asyncio
async def test_failed_import_diagnostic_is_registered_and_expires_after_24_hours(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    mutation = recipe_service(session_factory, tmp_path).create_import_placeholder(
        "https://example.com/invalid", trace_id="trace-diagnostic"
    )
    assert mutation.job is not None
    invalid_html = b"<html><body>not a recipe</body></html>"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=invalid_html,
            request=request,
        )
    )
    store = MediaStore(tmp_path / "media", "secret")
    importer = RecipeImporter(
        SafeFetcher(resolver=public_resolver, transport=transport),
        store,
        diagnostics_enabled=True,
    )
    worker = RecipePipeline(
        session_factory,
        importer,
        ImageServiceStub(),  # type: ignore[arg-type]
    )
    result = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert result.status == "failed"
    with session_factory() as session:
        asset = session.scalar(select(MediaAsset).where(MediaAsset.recipe_id == mutation.recipe.id))
        assert asset is not None
        assert asset.kind == "failed_import_diagnostic" and asset.encrypted is True
        assert asset.expires_at is not None
        storage_key = asset.storage_key
        expires_at = asset.expires_at
    assert store.read(storage_key, encrypted=True) == invalid_html

    swept = sweep_retention(
        JobService(session_factory),
        session_factory,
        store,
        now=expires_at,
    )
    assert swept["expired_media"] == 1
    with session_factory() as session:
        assert session.scalar(select(MediaAsset)) is None
    assert not store.resolve_key(storage_key).exists()
