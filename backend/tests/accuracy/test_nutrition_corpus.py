from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from vigor_vine.benchmark.nutrition_corpus import (
    CorpusObservation,
    MacroObservation,
    evaluate_scope,
    load_manifest,
    nutrient_summary,
    validate_snapshots,
)
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.recipe_importer import RecipeImporter
from vigor_vine.infrastructure.safe_fetch import SafeFetcher

CORPUS_ROOT = Path(__file__).parents[1] / "fixtures" / "nutrition-corpus"
MANIFEST = load_manifest(CORPUS_ROOT / "manifest.json")


async def public_resolver(_: str) -> set[str]:
    return {"93.184.216.34"}


@pytest.mark.nutrition_corpus
def test_corpus_distribution_and_snapshot_integrity() -> None:
    validate_snapshots(MANIFEST, CORPUS_ROOT)
    assert len(MANIFEST.cases) == 50
    assert sum(case.primary for case in MANIFEST.cases) == 30
    assert {case.source_site for case in MANIFEST.cases} == {
        "diabetesfoodhub.org",
        "www.bbcgoodfood.com",
        "www.recipetineats.com",
        "www.skinnytaste.com",
    }


@pytest.mark.nutrition_corpus
@pytest.mark.asyncio
async def test_all_captured_pages_pass_the_production_importer(tmp_path: Path) -> None:
    cases_by_host = {case.source_site: case for case in MANIFEST.cases}
    assert len(cases_by_host) == 4
    for case in MANIFEST.cases:
        content = (CORPUS_ROOT / case.snapshot).read_bytes()
        assert hashlib.sha256(content).hexdigest() == case.snapshot_sha256

        def response(request: httpx.Request, captured: bytes = content) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=captured,
                request=request,
            )

        importer = RecipeImporter(
            SafeFetcher(resolver=public_resolver, transport=httpx.MockTransport(response)),
            MediaStore(tmp_path / case.id, "benchmark-secret"),
        )
        imported = await importer.import_url(case.canonical_url)
        assert imported.title == case.expected_import.title
        assert imported.yield_text == case.expected_import.yield_text
        assert len(imported.ingredients) == case.expected_import.ingredient_count
        assert len(imported.instructions) == case.expected_import.instruction_count
        assert imported.source_nutrition


@pytest.mark.nutrition_corpus
def test_threshold_and_near_zero_formulas_are_exact() -> None:
    summary = nutrient_summary(
        "protein_g",
        [
            (Decimal("12"), Decimal("10")),
            (Decimal("9"), Decimal("10")),
            (Decimal("2.5"), Decimal("2")),
            (Decimal("0.5"), Decimal("0")),
        ],
    )
    assert summary.eligible_count == 2
    assert summary.near_zero_count == 2
    assert summary.median_percentage_error == Decimal("15.000000")
    assert summary.median_near_zero_absolute_error == Decimal("0.500000")
    assert summary.maximum_near_zero_absolute_error == Decimal("0.500000")
    assert summary.passed


@pytest.mark.nutrition_corpus
def test_source_values_cannot_satisfy_the_ingredient_derived_accuracy_gate() -> None:
    observations = [
        CorpusObservation(
            case_id=case.id,
            import_complete=True,
            macros=MacroObservation(
                calories_kcal=case.reference.calories_kcal,
                protein_g=case.reference.protein_g,
                carbohydrate_g=case.reference.carbohydrate_g,
                fat_g=case.reference.fat_g,
            ),
            coverage=Decimal("1"),
            provenance="source_provided",
        )
        for case in MANIFEST.cases
    ]
    report = evaluate_scope(MANIFEST.cases, observations)
    assert report.sc001_passed
    assert report.sc003_passed
    assert not report.sc002_passed
    assert report.ingredient_derived_count == 0
