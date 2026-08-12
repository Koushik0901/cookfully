from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from recipe_scrapers import scrape_html

from cookfully.benchmark.nutrition_corpus import (
    CorpusObservation,
    MacroObservation,
    derive_observations,
    evaluate_scope,
    load_derived_inputs,
    load_manifest,
    nutrient_summary,
    validate_snapshots,
)
from cookfully.cli.nutrition_report import build_report
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.recipe_importer import RecipeImporter
from cookfully.infrastructure.safe_fetch import SafeFetcher

CORPUS_ROOT = Path(__file__).parents[1] / "fixtures" / "nutrition-corpus"
MANIFEST = load_manifest(CORPUS_ROOT / "manifest.json")
DERIVED_INPUTS = load_derived_inputs(CORPUS_ROOT / "derived-inputs.json")


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


@pytest.mark.nutrition_corpus
def test_derived_inputs_align_with_captures_and_exclude_page_reference_macros() -> None:
    foods = {food.fdc_id for food in DERIVED_INPUTS.foods}
    derived_cases = {case.case_id: case for case in DERIVED_INPUTS.cases}
    assert {release.dataset_type for release in DERIVED_INPUTS.reference_releases} == {
        "foundation",
        "sr_legacy",
    }
    for case in MANIFEST.cases:
        derived = derived_cases[case.id]
        html = (CORPUS_ROOT / case.snapshot).read_text(encoding="utf-8")
        scraper = scrape_html(html, case.canonical_url, supported_only=False)
        lines = scraper.ingredients()
        assert [item.position for item in derived.ingredients] == list(range(len(lines)))
        assert [item.original_text for item in derived.ingredients] == lines
        assert all(item.assumption for item in derived.ingredients)
        assert all(
            item.food_fdc_id is None or item.food_fdc_id in foods for item in derived.ingredients
        )


@pytest.mark.nutrition_corpus
def test_full_and_primary_accuracy_gates_pass_with_near_zero_reporting() -> None:
    observations = derive_observations(MANIFEST, DERIVED_INPUTS)
    full = evaluate_scope(MANIFEST.cases, observations)
    primary_cases = [case for case in MANIFEST.cases if case.primary]
    by_id = {item.case_id: item for item in observations}
    primary = evaluate_scope(primary_cases, [by_id[case.id] for case in primary_cases])
    for report in (full, primary):
        assert report.sc001_passed
        assert report.sc002_passed
        assert report.sc003_passed
        assert all(summary.passed for summary in report.nutrients.values())
        assert report.nutrients["calories_kcal"].near_zero_count == 0
        assert all(
            report.nutrients[nutrient].near_zero_count > 0
            for nutrient in ("protein_g", "carbohydrate_g", "fat_g")
        )
    assert full.nutrition_complete_count == 49
    assert primary.nutrition_complete_count == 29


@pytest.mark.nutrition_corpus
def test_report_includes_full_primary_source_and_complexity_breakdowns() -> None:
    report = build_report(CORPUS_ROOT)
    assert set(report["bySourceSite"]) == {case.source_site for case in MANIFEST.cases}
    assert set(report["byComplexity"]) == {"simple", "moderate", "complex"}
    for scope in ("full", "primary"):
        result = report[scope]
        assert isinstance(result, dict)
        assert result["sc001Passed"] and result["sc002Passed"] and result["sc003Passed"]
