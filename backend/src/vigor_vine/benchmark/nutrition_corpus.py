from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from vigor_vine.domain.common import NUTRIENT_SCALE, quantize_decimal

Complexity = Literal["simple", "moderate", "complex"]
NutrientName = Literal["calories_kcal", "protein_g", "carbohydrate_g", "fat_g"]
Provenance = Literal["ingredient_derived", "source_provided", "manual"]

NEAR_ZERO_FLOORS: dict[NutrientName, Decimal] = {
    "calories_kcal": Decimal("50"),
    "protein_g": Decimal("5"),
    "carbohydrate_g": Decimal("5"),
    "fat_g": Decimal("2"),
}
PERCENTAGE_THRESHOLDS: dict[NutrientName, Decimal] = {
    "calories_kcal": Decimal("20"),
    "protein_g": Decimal("25"),
    "carbohydrate_g": Decimal("25"),
    "fat_g": Decimal("25"),
}


class ImportExpectation(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    title: str
    yield_text: str
    ingredient_count: int = Field(ge=1)
    instruction_count: int = Field(ge=1)


class ReferenceMacros(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    basis: Literal["per-serving"]
    yield_text: str
    calories_kcal: Decimal = Field(ge=0)
    protein_g: Decimal = Field(ge=0)
    carbohydrate_g: Decimal = Field(ge=0)
    fat_g: Decimal = Field(ge=0)


class Classification(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    unit_systems: list[str] = Field(min_length=1)
    risk_tags: list[str] = Field(min_length=1)


class CorpusCase(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str = Field(pattern=r"^NR-\d{3}$")
    slug: str
    url: str
    complexity: Complexity
    primary: bool
    cuisine: str
    dietary_pattern: str
    source_site: str
    canonical_url: str
    snapshot: str
    source_html_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_import: ImportExpectation
    reference: ReferenceMacros
    classification: Classification


class CorpusManifest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    schema_version: Literal[1]
    corpus_version: str
    captured_at: str
    capture_policy: str
    reference_policy: str
    cases: list[CorpusCase]

    @model_validator(mode="after")
    def validate_distribution(self) -> CorpusManifest:
        if len(self.cases) != 50 or len({case.id for case in self.cases}) != 50:
            raise ValueError("nutrition corpus must contain 50 uniquely identified cases")
        distribution = {
            level: sum(case.complexity == level for case in self.cases)
            for level in ("simple", "moderate", "complex")
        }
        if distribution != {"simple": 15, "moderate": 20, "complex": 15}:
            raise ValueError(f"invalid complexity distribution: {distribution}")
        primary = [case for case in self.cases if case.primary]
        if len(primary) != 30:
            raise ValueError("nutrition corpus must contain a stable 30-case primary subset")
        primary_distribution = {
            level: sum(case.complexity == level for case in primary)
            for level in ("simple", "moderate", "complex")
        }
        if primary_distribution != {"simple": 9, "moderate": 12, "complex": 9}:
            raise ValueError(f"invalid primary distribution: {primary_distribution}")
        if len({case.source_site for case in self.cases}) < 3:
            raise ValueError("nutrition corpus must span at least three source sites")
        if len({case.cuisine for case in self.cases}) < 6:
            raise ValueError("nutrition corpus must span at least six cuisine classifications")
        if len({case.dietary_pattern for case in self.cases}) < 4:
            raise ValueError("nutrition corpus must span at least four dietary patterns")
        return self


class MacroObservation(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    calories_kcal: Decimal | None
    protein_g: Decimal | None
    carbohydrate_g: Decimal | None
    fat_g: Decimal | None


class CorpusObservation(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    case_id: str
    import_complete: bool
    macros: MacroObservation
    coverage: Decimal = Field(ge=0, le=1)
    provenance: Provenance
    discrepancy_classifications: list[
        Literal[
            "parse",
            "match",
            "conversion",
            "yield",
            "reference-data",
            "benchmark-eligibility",
        ]
    ] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NutrientSummary:
    eligible_count: int
    near_zero_count: int
    median_percentage_error: Decimal | None
    median_near_zero_absolute_error: Decimal | None
    maximum_near_zero_absolute_error: Decimal | None
    threshold: Decimal
    passed: bool


@dataclass(frozen=True, slots=True)
class ScopeReport:
    case_count: int
    import_complete_count: int
    nutrition_complete_count: int
    ingredient_derived_count: int
    import_rate: Decimal
    nutrition_complete_rate: Decimal
    nutrients: dict[NutrientName, NutrientSummary]
    sc001_passed: bool
    sc002_passed: bool
    sc003_passed: bool


def load_manifest(path: Path) -> CorpusManifest:
    return CorpusManifest.model_validate_json(path.read_text(encoding="utf-8"))


def validate_snapshots(manifest: CorpusManifest, corpus_root: Path) -> None:
    root = corpus_root.resolve()
    for case in manifest.cases:
        snapshot = (corpus_root / case.snapshot).resolve()
        if root not in snapshot.parents:
            raise ValueError(f"snapshot escapes corpus root: {case.snapshot}")
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        if digest != case.snapshot_sha256:
            raise ValueError(f"snapshot digest mismatch for {case.id}")


def percentage_error(estimate: Decimal, reference: Decimal) -> Decimal:
    if reference <= 0:
        raise ValueError("percentage error requires a positive reference")
    return quantize_decimal(abs(estimate - reference) / reference * 100, NUTRIENT_SCALE)


def nutrient_summary(
    nutrient: NutrientName,
    pairs: list[tuple[Decimal, Decimal]],
) -> NutrientSummary:
    floor = NEAR_ZERO_FLOORS[nutrient]
    threshold = PERCENTAGE_THRESHOLDS[nutrient]
    percentage_errors = [
        percentage_error(estimate, reference) for estimate, reference in pairs if reference >= floor
    ]
    absolute_errors = [
        quantize_decimal(abs(estimate - reference), NUTRIENT_SCALE)
        for estimate, reference in pairs
        if reference < floor
    ]
    median_percentage = _median(percentage_errors)
    return NutrientSummary(
        eligible_count=len(percentage_errors),
        near_zero_count=len(absolute_errors),
        median_percentage_error=median_percentage,
        median_near_zero_absolute_error=_median(absolute_errors),
        maximum_near_zero_absolute_error=max(absolute_errors, default=None),
        threshold=threshold,
        passed=median_percentage is not None and median_percentage <= threshold,
    )


def evaluate_scope(cases: list[CorpusCase], observations: list[CorpusObservation]) -> ScopeReport:
    observations_by_id = {item.case_id: item for item in observations}
    if len(observations_by_id) != len(observations):
        raise ValueError("duplicate corpus observation")
    unknown = set(observations_by_id) - {case.id for case in cases}
    if unknown:
        raise ValueError(f"unknown corpus observations: {sorted(unknown)}")
    scoped = [(case, observations_by_id.get(case.id)) for case in cases]
    import_count = sum(
        observation is not None and observation.import_complete for _, observation in scoped
    )
    nutrition_complete_count = sum(
        observation is not None
        and observation.coverage >= Decimal("0.900000")
        and all(
            value is not None
            for value in (
                observation.macros.calories_kcal,
                observation.macros.protein_g,
                observation.macros.carbohydrate_g,
                observation.macros.fat_g,
            )
        )
        for _, observation in scoped
    )
    derived = [
        (case, observation)
        for case, observation in scoped
        if observation is not None and observation.provenance == "ingredient_derived"
    ]
    summaries: dict[NutrientName, NutrientSummary] = {}
    for nutrient in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g"):
        pairs: list[tuple[Decimal, Decimal]] = []
        for case, observation in derived:
            estimate = getattr(observation.macros, nutrient)
            reference = getattr(case.reference, nutrient)
            if estimate is not None:
                pairs.append((estimate, reference))
        summaries[nutrient] = nutrient_summary(nutrient, pairs)
    case_count = len(cases)
    import_rate = _ratio(import_count, case_count)
    complete_rate = _ratio(nutrition_complete_count, case_count)
    return ScopeReport(
        case_count=case_count,
        import_complete_count=import_count,
        nutrition_complete_count=nutrition_complete_count,
        ingredient_derived_count=len(derived),
        import_rate=import_rate,
        nutrition_complete_rate=complete_rate,
        nutrients=summaries,
        sc001_passed=complete_rate >= Decimal("0.900000"),
        sc002_passed=len(derived) == case_count and all(item.passed for item in summaries.values()),
        sc003_passed=import_rate >= Decimal("0.900000"),
    )


def report_as_json(report: ScopeReport) -> dict[str, Any]:
    return {
        "caseCount": report.case_count,
        "importCompleteCount": report.import_complete_count,
        "nutritionCompleteCount": report.nutrition_complete_count,
        "ingredientDerivedCount": report.ingredient_derived_count,
        "importRate": str(report.import_rate),
        "nutritionCompleteRate": str(report.nutrition_complete_rate),
        "sc001Passed": report.sc001_passed,
        "sc002Passed": report.sc002_passed,
        "sc003Passed": report.sc003_passed,
        "nutrients": {
            nutrient: {
                "eligibleCount": summary.eligible_count,
                "nearZeroCount": summary.near_zero_count,
                "medianPercentageError": _string_or_none(summary.median_percentage_error),
                "medianNearZeroAbsoluteError": _string_or_none(
                    summary.median_near_zero_absolute_error
                ),
                "maximumNearZeroAbsoluteError": _string_or_none(
                    summary.maximum_near_zero_absolute_error
                ),
                "threshold": str(summary.threshold),
                "passed": summary.passed,
            }
            for nutrient, summary in report.nutrients.items()
        },
    }


def write_report(path: Path, report: ScopeReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report_as_json(report), indent=2) + "\n", encoding="utf-8")


def _median(values: list[Decimal]) -> Decimal | None:
    return quantize_decimal(median(values), NUTRIENT_SCALE) if values else None


def _ratio(numerator: int, denominator: int) -> Decimal:
    return quantize_decimal(Decimal(numerator) / Decimal(denominator or 1), NUTRIENT_SCALE)


def _string_or_none(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None
