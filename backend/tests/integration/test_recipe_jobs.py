from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.auth import AuthService
from cookfully.application.corrections import CorrectionService
from cookfully.application.jobs import JobService
from cookfully.application.recipes import IngredientWrite, RecipeService, RecipeWrite
from cookfully.domain.common import DomainError, uuid7
from cookfully.infrastructure.erasure_ledger import ErasureLedger
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.jobs import OutboxEvent, ProcessingJob
from cookfully.infrastructure.models.media import MediaAsset
from cookfully.infrastructure.models.nutrition import NutritionCorrection, NutritionEstimate
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
    ReferenceDataset,
)
from cookfully.infrastructure.recipe_importer import (
    ImportedCookbook,
    ImportedRecipe,
    RecipeImporter,
)
from cookfully.infrastructure.repositories.recipes import RecipeRepository
from cookfully.infrastructure.safe_fetch import SafeFetcher
from cookfully.jobs.recipe_pipeline import JobEnvelope, RecipePipeline
from cookfully.jobs.retention import sweep_retention


class ImporterStub:
    def __init__(self, result: ImportedRecipe | ImportedCookbook | DomainError) -> None:
        self.result = result
        self.calls = 0

    async def import_url(self, url: str) -> ImportedRecipe | ImportedCookbook:
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


def bootstrap_owner_id(session_factory: sessionmaker[Session]) -> UUID:
    return (
        AuthService(session_factory)
        .bootstrap_owner("owner@example.com", "correct horse battery staple", "Owner")
        .id
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
                FoodNutrient(
                    nutrient_code="291",
                    canonical_key="dietary_fiber_g",
                    mapping_version="usda-fdc-2026-04-v1",
                    amount=Decimal("0"),
                    unit="g",
                    explicit_zero=True,
                ),
                FoodNutrient(
                    nutrient_code="306",
                    canonical_key="potassium_mg",
                    mapping_version="usda-fdc-2026-04-v1",
                    amount=Decimal("256"),
                    unit="mg",
                ),
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
    mutation = recipe_service(session_factory, tmp_path).create(
        write(), trace_id="trace-chain", owner_id=owner.id
    )
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
    with session_factory() as session:
        parse_job = session.get(ProcessingJob, mutation.job.id)
        assert parse_job is not None
        assert (parse_job.progress_current, parse_job.progress_total) == (1, 1)
    matched = await worker.process(envelope_for(session_factory, parsed.next_job_id))
    assert matched.status == "succeeded" and matched.next_job_id is not None
    with session_factory() as session:
        match_job = session.get(ProcessingJob, parsed.next_job_id)
        assert match_job is not None
        assert (match_job.progress_current, match_job.progress_total) == (1, 1)
    rolled_up = await worker.process(envelope_for(session_factory, matched.next_job_id))
    assert rolled_up.status == "succeeded" and rolled_up.next_job_id is None
    with session_factory() as session:
        rollup_job = session.get(ProcessingJob, matched.next_job_id)
        assert rollup_job is not None
        assert (rollup_job.progress_current, rollup_job.progress_total) == (1, 1)

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
        assert estimate.fiber_g == Decimal("0.000000")
        assert estimate.potassium_mg == Decimal("256.000000")
        assert estimate.micronutrient_mapping_version == "usda-fdc-2026-04-v1"
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
            ingredient_sections=(None,),
            sections=(),
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
        assert source.coverage_ratio == Decimal("0.000000")


@pytest.mark.asyncio
async def test_source_estimate_coverage_updated_to_real_ingredient_coverage_after_rollup(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    install_reference_data(session_factory)
    mutation = recipe_service(session_factory, tmp_path).create_import_placeholder(
        "https://example.com/mixed", trace_id="trace-mixed"
    )
    assert mutation.job is not None
    importer = ImporterStub(
        ImportedRecipe(
            title="Mixed source",
            source_url="https://example.com/mixed",
            canonical_url="https://example.com/mixed",
            image_url=None,
            yield_quantity=Decimal("2.000"),
            yield_text="2 servings",
            ingredients=("200 g chicken breast", "1 cup mystery protein"),
            ingredient_sections=(None, None),
            sections=(),
            instructions=("Cook.",),
            source_nutrition={
                "calories": "500 kcal",
                "proteinContent": "40 g",
                "carbohydrateContent": "20 g",
                "fatContent": "20 g",
            },
        )
    )
    worker = pipeline(session_factory, importer)
    imported = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert imported.status == "succeeded" and imported.next_job_id is not None
    parsed = await worker.process(envelope_for(session_factory, imported.next_job_id))
    assert parsed.status == "succeeded" and parsed.next_job_id is not None
    matched = await worker.process(envelope_for(session_factory, parsed.next_job_id))
    assert matched.status == "succeeded" and matched.next_job_id is not None
    rollup = await worker.process(envelope_for(session_factory, matched.next_job_id))
    assert rollup.status == "succeeded"
    with session_factory() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        assert recipe is not None and recipe.status == "ready"
        assert recipe.nutrition_state == "source_provided"
        active = session.get(NutritionEstimate, recipe.active_estimate_id)
        assert active is not None and active.status == "source_provided"
        assert active.coverage_ratio == Decimal("0.500000")


@pytest.mark.asyncio
async def test_cookbook_import_creates_each_recipe_and_queues_each_parse_atomically(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    mutation = recipe_service(session_factory, tmp_path).create_import_placeholder(
        "https://example.com/book.pdf", trace_id="trace-cookbook"
    )
    assert mutation.job is not None
    first = ImportedRecipe(
        "First recipe",
        "https://example.com/book.pdf",
        "https://example.com/book.pdf",
        None,
        None,
        None,
        ("1 cup oats",),
        (None,),
        (),
        ("Cook the oats.",),
        {},
    )
    second = ImportedRecipe(
        "Second recipe",
        "https://example.com/book.pdf",
        "https://example.com/book.pdf",
        None,
        None,
        None,
        ("1 cup rice",),
        (None,),
        (),
        ("Cook the rice.",),
        {},
    )
    worker = pipeline(
        session_factory,
        ImporterStub(
            ImportedCookbook(
                "Two recipes",
                "https://example.com/book.pdf",
                "https://example.com/book.pdf",
                (first, second),
            )
        ),
    )
    result = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert result.status == "succeeded" and result.next_job_id is not None
    with session_factory() as session:
        recipes = list(session.scalars(select(Recipe).order_by(Recipe.title)))
        parse_jobs = list(
            session.scalars(select(ProcessingJob).where(ProcessingJob.kind == "ingredient_parse"))
        )
        assert [item.title for item in recipes] == ["First recipe", "Second recipe"]
        assert all(item.yield_unit == "batch" for item in recipes)
        assert len(parse_jobs) == 2


@pytest.mark.asyncio
async def test_input_change_and_archive_supersede_queued_work(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    recipes = recipe_service(session_factory, tmp_path)
    owner_id = bootstrap_owner_id(session_factory)
    changed = recipes.create(write(), trace_id="trace-changed", owner_id=owner_id)
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

    archived = recipes.create(write(), trace_id="trace-archive", owner_id=owner_id)
    assert archived.job is not None
    recipes.archive(archived.recipe.id, expected_version=1)
    result = await worker.process(envelope_for(session_factory, archived.job.id))
    assert result.status == "superseded"


@pytest.mark.asyncio
async def test_missing_reference_data_retries_instead_of_blocking_manual_use(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    mutation = recipe_service(session_factory, tmp_path).create(
        write(), trace_id="trace-degraded", owner_id=bootstrap_owner_id(session_factory)
    )
    assert mutation.job is not None
    worker = pipeline(
        session_factory,
        ImporterStub(DomainError("not_used", "Not used.", 500)),
    )
    parsed = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert parsed.next_job_id is not None
    result = await worker.process(envelope_for(session_factory, parsed.next_job_id))
    assert result.status == "retry_wait"
    with session_factory() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        job = session.get(ProcessingJob, parsed.next_job_id)
        assert recipe is not None and recipe.status == "processing"
        assert recipe.nutrition_state == "pending"
        assert job is not None and job.failure_code == "reference_data_unavailable"
        assert job.status == "retry_wait" and job.next_retry_at is not None
        assert job.max_attempts == 5


@pytest.mark.asyncio
async def test_reference_data_retry_completes_once_data_is_active(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    mutation = recipe_service(session_factory, tmp_path).create(
        write(), trace_id="trace-recovery", owner_id=bootstrap_owner_id(session_factory)
    )
    assert mutation.job is not None
    worker = pipeline(
        session_factory,
        ImporterStub(DomainError("not_used", "Not used.", 500)),
    )
    parsed = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert parsed.next_job_id is not None
    match_job_id = parsed.next_job_id
    retry = await worker.process(envelope_for(session_factory, match_job_id))
    assert retry.status == "retry_wait"
    with session_factory() as session:
        job = session.get(ProcessingJob, match_job_id)
        assert job is not None and job.next_retry_at is not None
        retry_at = job.next_retry_at

    install_reference_data(session_factory)
    released_at = retry_at + timedelta(minutes=5)
    assert JobService(session_factory).release_due_retries(now=released_at) == [match_job_id]
    with session_factory.begin() as session:
        job = session.get(ProcessingJob, match_job_id)
        assert job is not None and job.status == "queued"
        job.available_at = datetime.now(UTC)

    succeeded = await worker.process(envelope_for(session_factory, match_job_id))
    assert succeeded.status == "succeeded"
    assert succeeded.next_job_id is not None
    rollup = await worker.process(envelope_for(session_factory, succeeded.next_job_id))
    assert rollup.status == "succeeded"
    with session_factory() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        estimate = session.get(NutritionEstimate, recipe.active_estimate_id)
        assert recipe is not None and recipe.status == "ready"
        assert estimate is not None and estimate.status == "estimated"
        assert estimate.coverage_ratio == Decimal("1.000000")


@pytest.mark.asyncio
async def test_recover_stale_nutrition_dry_run_then_enqueues_when_reference_data_active(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    services = recipe_service(session_factory, tmp_path)
    mutation = services.create(
        write(), trace_id="trace-stale", owner_id=bootstrap_owner_id(session_factory)
    )
    assert mutation.job is not None
    worker = pipeline(
        session_factory,
        ImporterStub(DomainError("not_used", "Not used.", 500)),
    )
    parsed = await worker.process(envelope_for(session_factory, mutation.job.id))
    assert parsed.next_job_id is not None
    now = datetime.now(UTC)
    with session_factory.begin() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        job = session.get(ProcessingJob, parsed.next_job_id)
        assert recipe is not None and job is not None
        job.status = "failed"
        job.failure_code = "reference_data_unavailable"
        job.finished_at = now
        job.next_retry_at = None
        recipe.status = "partial"
        recipe.nutrition_state = "partial"
        recipe.version += 1

    dry_run = services.recover_stale_nutrition(dry_run=True)
    assert [item.recipe_id for item in dry_run] == [mutation.recipe.id]
    assert all(item.skipped_reason == "reference_data_unavailable" for item in dry_run)
    with session_factory() as session:
        active = list(
            session.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.aggregate_id == mutation.recipe.id,
                    ProcessingJob.status.in_(("queued", "running", "retry_wait")),
                )
            )
        )
        assert active == []

    install_reference_data(session_factory)
    dry_run = services.recover_stale_nutrition(dry_run=True)
    assert all(item.skipped_reason == "dry_run" and item.job_id is None for item in dry_run)

    waiting = services.recover_stale_nutrition(dry_run=False)
    assert [item.recipe_id for item in waiting] == [mutation.recipe.id]
    assert all(item.skipped_reason is None and item.job_id is not None for item in waiting)
    with session_factory() as session:
        recipe = session.get(Recipe, mutation.recipe.id)
        job = session.get(ProcessingJob, waiting[0].job_id)
        assert recipe is not None and recipe.status == "processing"
        assert recipe.nutrition_state == "stale"
        assert job is not None and job.kind == "nutrition_match"
        assert job.input_hash == recipe.input_hash
        assert job.status == "queued"

    idempotent = services.recover_stale_nutrition(dry_run=False)
    assert idempotent == []
    with session_factory() as session:
        active = list(
            session.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.aggregate_id == mutation.recipe.id,
                    ProcessingJob.status.in_(("queued", "running", "retry_wait")),
                )
            )
        )
        assert [job.id for job in active] == [waiting[0].job_id]

    resumed = await worker.process(envelope_for(session_factory, waiting[0].job_id))
    assert resumed.status == "succeeded"
    assert resumed.next_job_id is not None
    rollup = await worker.process(envelope_for(session_factory, resumed.next_job_id))
    assert rollup.status == "succeeded"


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
        failed_recipe = session.get(Recipe, mutation.recipe.id)
        assert failed_recipe is not None and failed_recipe.status == "import_failed"
        assert mutation.recipe.id not in {
            item.id for item in RecipeRepository(session).list_recipes(include_archived=True)
        }
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
