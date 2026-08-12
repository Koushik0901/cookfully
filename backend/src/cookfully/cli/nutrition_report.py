from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from cookfully.benchmark.nutrition_corpus import (
    CorpusCase,
    derive_observations,
    evaluate_scope,
    load_derived_inputs,
    load_manifest,
    report_as_json,
    validate_snapshots,
)

app = typer.Typer(name="nutrition-corpus", help="Evaluate the versioned recipe nutrition corpus.")
DEFAULT_CORPUS_ROOT = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "nutrition-corpus"
)


def build_report(corpus_root: Path) -> dict[str, object]:
    manifest = load_manifest(corpus_root / "manifest.json")
    inputs = load_derived_inputs(corpus_root / "derived-inputs.json")
    validate_snapshots(manifest, corpus_root)
    observations = derive_observations(manifest, inputs)
    by_id = {item.case_id: item for item in observations}

    def evaluate(cases: list[CorpusCase]) -> dict[str, object]:
        return report_as_json(evaluate_scope(cases, [by_id[case.id] for case in cases]))

    primary = [case for case in manifest.cases if case.primary]
    source_sites = sorted({case.source_site for case in manifest.cases})
    return {
        "schemaVersion": 1,
        "corpusVersion": manifest.corpus_version,
        "referenceReleases": [
            release.model_dump(by_alias=True, mode="json") for release in inputs.reference_releases
        ],
        "full": evaluate(manifest.cases),
        "primary": evaluate(primary),
        "bySourceSite": {
            site: evaluate([case for case in manifest.cases if case.source_site == site])
            for site in source_sites
        },
        "byComplexity": {
            complexity: evaluate([case for case in manifest.cases if case.complexity == complexity])
            for complexity in ("simple", "moderate", "complex")
        },
        "caseObservations": [item.model_dump(by_alias=True, mode="json") for item in observations],
    }


@app.command("run")
def run(
    corpus_root: Annotated[Path, typer.Option(exists=True, file_okay=False)] = DEFAULT_CORPUS_ROOT,
    output: Annotated[Path | None, typer.Option()] = None,
    require_pass: Annotated[bool, typer.Option()] = False,
) -> None:
    """Build the full, primary, source-site, and complexity accuracy report."""

    report = build_report(corpus_root)
    destination = output or corpus_root / "reports" / "nutrition-accuracy.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    typer.echo(
        json.dumps(
            {"output": str(destination), "full": report["full"], "primary": report["primary"]},
            indent=2,
        )
    )
    if require_pass:
        required = ("sc001Passed", "sc002Passed", "sc003Passed")
        for scope in ("primary", "full"):
            result = report[scope]
            assert isinstance(result, dict)
            if not all(result.get(key) is True for key in required):
                raise typer.Exit(1)
