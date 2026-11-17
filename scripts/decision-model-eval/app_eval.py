"""Evaluate decision-model features with the application's own code.

Unlike the ``exp*`` scripts (stdlib-only experiments with their own client), this runner drives the
code that ships: the deterministic ``FoodMatcher``, the ``Decisions`` engine and each feature's rule.
Model answers are cached in ``<workdir>/decision_cache.jsonl`` through a file-backed engine store, so
a rerun with the same prompts makes no calls and costs nothing; with ``--offline`` a cache miss is
reported instead of called.

Usage (from the repo root):

    uv run --directory backend python ../scripts/decision-model-eval/app_eval.py \\
        --usda-dir <dir with the two pinned USDA zips> --workdir <dir> match-assist

The OpenRouter key is never read here: the transport sends ``Authorization: Bearer $OPENROUTER_API_KEY``
(set it to your key, or to a placeholder where a proxy injects the real one).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from usda_pool import StubNutritionRepository

from cookfully.application.decision_assist import AssistLine, DecisionAssist
from cookfully.application.decisions import (
    DECISIONS_URL,
    Decisions,
    DecisionsConfig,
    FeatureConfig,
)
from cookfully.domain.common import uuid7
from cookfully.domain.decisions import Purpose
from cookfully.domain.ingredient_nutrition.matching import (
    FoodCandidate,
    FoodMatcher,
    MatchDecision,
)
from cookfully.domain.ingredient_nutrition.normalization import normalize
from cookfully.infrastructure.decision_client import (
    OpenRouterDecisionTransport,
    RawDecision,
)
from cookfully.infrastructure.decision_store import StoredAnswer
from cookfully.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
)

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "backend/tests/fixtures/nutrition-corpus"
RESULTS = ROOT / "docs/decision-model-experiments/results"
FOUNDATION_ZIP = "FoodData_Central_foundation_food_json_2024-04-18.zip"
SR_LEGACY_ZIP = "FoodData_Central_sr_legacy_food_json_2018-04.zip"
JEV, CLEF = "typesafe/jev-1.14", "cloudflare/clef"
PANELS: dict[str, tuple[str, ...]] = {"jev": (JEV,), "clef": (CLEF,), "jev+clef": (JEV, CLEF)}


# --- data ---------------------------------------------------------------------------------------


def load_foods(usda_dir: Path) -> list[FoodReference]:
    """Pinned Foundation + SR Legacy foods with their nutrients, as transient ORM rows."""

    foods: list[FoodReference] = []
    for name, data_type in ((FOUNDATION_ZIP, "foundation"), (SR_LEGACY_ZIP, "sr_legacy")):
        with zipfile.ZipFile(usda_dir / name) as archive:
            raw = json.loads(archive.read(archive.namelist()[0]))
        dataset_id = uuid7()
        for item in next(value for value in raw.values() if isinstance(value, list)):
            if not item:
                continue
            food = FoodReference(
                id=uuid7(),
                dataset_id=dataset_id,
                external_id=str(item["fdcId"]),
                description=item["description"],
                normalized_name=normalize(item["description"]),
                data_type=data_type,
                food_category=(item.get("foodCategory") or {}).get("description"),
                basis_grams=Decimal(100),
            )
            nutrients = []
            for entry in item.get("foodNutrients") or []:
                nutrient = entry.get("nutrient") or {}
                if entry.get("amount") is None or not nutrient:
                    continue
                amount = Decimal(str(entry["amount"]))
                for code in {str(nutrient.get("id")), str(nutrient.get("number"))}:
                    if code and code != "None":
                        nutrients.append(
                            FoodNutrient(
                                nutrient_code=code, amount=amount, unit="", canonical_key=None
                            )
                        )
            food.nutrients = nutrients
            foods.append(food)
    return foods


@dataclass(frozen=True, slots=True)
class CorpusLine:
    idx: int
    case_id: str
    recipe_title: str
    original_text: str
    food_name: str
    grams: Decimal | None


def corpus_lines() -> list[CorpusLine]:
    """Every corpus ingredient line, numbered exactly as the PR #12 gold labels are."""

    derived = json.loads((CORPUS / "derived-inputs.json").read_text("utf-8"))
    manifest = json.loads((CORPUS / "manifest.json").read_text("utf-8"))
    titles = {case["id"]: case["slug"].replace("-", " ") for case in manifest["cases"]}
    lines: list[CorpusLine] = []
    for case in derived["cases"]:
        for ingredient in case["ingredients"]:
            lines.append(
                CorpusLine(
                    len(lines),
                    case["caseId"],
                    titles.get(case["caseId"], ""),
                    ingredient["originalText"],
                    ingredient["parsedFoodName"] or ingredient["originalText"],
                    Decimal(ingredient["grams"]) if ingredient.get("grams") else None,
                )
            )
    return lines


def gold_labels() -> dict[int, dict[str, Any]]:
    raw = json.loads((RESULTS / "gold_labels.json").read_text("utf-8"))
    return {int(key): value for key, value in raw.items()}


# --- engine with a file cache -----------------------------------------------------------------------


@dataclass
class FileDecisionStore:
    """Engine store backed by an append-only JSONL file in the workdir."""

    path: Path
    rows: dict[tuple[str, str], StoredAnswer] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.path.is_file():
            for line in self.path.read_text("utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    stored = StoredAnswer(
                        row["purpose"],
                        row["model"],
                        row["request_hash"],
                        row["answers"],
                        Decimal(row["cost_usd"]),
                        row.get("served_model"),
                    )
                    self.rows[(stored.model, stored.request_hash)] = stored

    def get(self, keys: Sequence[tuple[str, str]]) -> dict[tuple[str, str], StoredAnswer]:
        return {key: self.rows[key] for key in keys if key in self.rows}

    def put(self, rows: Sequence[StoredAnswer]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            for row in rows:
                key = (row.model, row.request_hash)
                if key in self.rows:
                    continue
                self.rows[key] = row
                handle.write(
                    json.dumps(
                        {
                            "purpose": row.purpose,
                            "model": row.model,
                            "request_hash": row.request_hash,
                            "answers": row.answers,
                            "cost_usd": str(row.cost_usd),
                            "served_model": row.served_model,
                        }
                    )
                    + "\n"
                )

    def spent_since(self, since: datetime) -> Decimal:
        del since  # the cap here is per run; see ``budget`` below
        return Decimal(0)

    def total_cost(self) -> Decimal:
        return sum((row.cost_usd for row in self.rows.values()), Decimal(0))


@dataclass
class OfflineTransport:
    """Counts cache misses instead of calling the API."""

    misses: int = 0

    def post(self, model: str, state: Any, questions: Any) -> RawDecision | None:
        del model, state, questions
        self.misses += 1
        return None


@dataclass
class Harness:
    store: FileDecisionStore
    offline: bool
    budget_usd: Decimal
    offline_transport: OfflineTransport = field(default_factory=OfflineTransport)

    def engine(self, purpose: Purpose, models: tuple[str, ...]) -> Decisions:
        transport: Any
        if self.offline:
            transport = self.offline_transport
        else:
            transport = OpenRouterDecisionTransport(
                api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                url=DECISIONS_URL,
                timeout_seconds=60,
            )
        spent = self.store.total_cost()
        return Decisions(
            DecisionsConfig(
                "eval", self.budget_usd - spent, {purpose: FeatureConfig(True, models)}
            ),
            transport,
            self.store,
        )


# --- matching ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MatchCase:
    line: CorpusLine
    gold: Mapping[str, Any]
    decision: MatchDecision

    @property
    def candidates(self) -> tuple[FoodCandidate, ...]:
        head = (self.decision.candidate,) if self.decision.candidate is not None else ()
        return head + self.decision.alternatives

    def correct(self, food: FoodReference | None) -> bool:
        """A food is correct when gold accepts it; for non-foods, only "no match" is correct."""

        if self.gold["kind"] in {"food", "multi"}:
            return food is not None and food.external_id in self.gold["acceptable"]
        return food is None


def match_cases(usda_dir: Path) -> list[MatchCase]:
    foods = load_foods(usda_dir)
    matcher = FoodMatcher(StubNutritionRepository(foods), candidate_pool_limit=256)  # type: ignore[arg-type]
    gold = gold_labels()
    lines = {line.idx: line for line in corpus_lines()}
    return [
        MatchCase(lines[idx], label, matcher.decide(lines[idx].food_name))
        for idx, label in sorted(gold.items())
    ]


def assist_line(case: MatchCase) -> AssistLine:
    return AssistLine(
        case.line.original_text, case.line.food_name, case.line.recipe_title, case.line.grams
    )


def report_match_assist(harness: Harness, cases: list[MatchCase], tolerances: Iterable[str]) -> str:
    out = [_deterministic_summary(cases), ""]
    out.append("Assist on ambiguous/unmatched lines (the shipped rule), per panel and tolerance:")
    out.append(
        f"{'panel':<10}{'tol':>6}{'eligible':>10}{'resolved':>10}{'correct':>9}"
        f"{'wrong':>7}{'precision':>11}"
    )
    eligible = [case for case in cases if case.decision.status != "matched" and case.candidates]
    for name, models in PANELS.items():
        for tolerance in tolerances:
            assist = DecisionAssist(
                harness.engine(Purpose.MATCH_REFEREE, models), tolerance_dv=Decimal(tolerance)
            )
            resolved = correct = 0
            for case in eligible:
                outcome = assist.resolve(assist_line(case), case.candidates)
                if outcome is None:
                    continue
                resolved += 1
                if case.correct(outcome.candidate.food):
                    correct += 1
            precision = f"{correct / resolved:.0%}" if resolved else "-"
            out.append(
                f"{name:<10}{tolerance:>6}{len(eligible):>10}{resolved:>10}{correct:>9}"
                f"{resolved - correct:>7}{precision:>11}"
            )
    return "\n".join(out)


def _deterministic_summary(cases: list[MatchCase]) -> str:
    by_status: dict[str, Counter[str]] = defaultdict(Counter)
    for case in cases:
        food = case.decision.candidate.food if case.decision.candidate else None
        verdict = "correct" if case.correct(food) else "wrong"
        by_status[case.decision.status][verdict] += 1
    parts = [
        f"Gold lines: {len(cases)} (strata: {dict(Counter(c.gold['stratum'] for c in cases))})"
    ]
    for status, counts in sorted(by_status.items()):
        parts.append(
            f"  deterministic {status:<10} correct={counts['correct']} wrong={counts['wrong']}"
        )
    return "\n".join(parts)


# --- entry point ---------------------------------------------------------------------------------

Evaluator = Callable[[Harness, argparse.Namespace], str]


def _match_assist(harness: Harness, args: argparse.Namespace) -> str:
    return report_match_assist(harness, match_cases(args.usda_dir), args.tolerance)


EVALUATORS: dict[str, Evaluator] = {"match-assist": _match_assist}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--usda-dir", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--offline", action="store_true", help="never call; report cache misses")
    parser.add_argument(
        "--budget", type=Decimal, default=Decimal("1.00"), help="USD cap for the cache"
    )
    parser.add_argument("--tolerance", nargs="+", default=["0.01", "0.02", "0.05"])
    parser.add_argument("evaluator", choices=sorted(EVALUATORS))
    args = parser.parse_args(argv)
    args.workdir.mkdir(parents=True, exist_ok=True)
    harness = Harness(
        FileDecisionStore(args.workdir / "decision_cache.jsonl"), args.offline, args.budget
    )
    started = datetime.now(UTC)
    print(EVALUATORS[args.evaluator](harness, args))
    print(
        f"\ncache: {len(harness.store.rows)} answers, ${harness.store.total_cost():.4f} total"
        f"; offline misses: {harness.offline_transport.misses}"
        f"; {(datetime.now(UTC) - started).total_seconds():.0f}s"
    )


if __name__ == "__main__":
    main()
