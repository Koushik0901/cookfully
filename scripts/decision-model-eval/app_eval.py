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

from cookfully.application.match_referee import MatchReferee, RefereeLine
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


def referee_line(case: MatchCase) -> RefereeLine:
    return RefereeLine(
        case.line.original_text, case.line.food_name, case.line.recipe_title, case.line.grams
    )


def report_match_referee(
    harness: Harness, cases: list[MatchCase], tolerances: Iterable[str]
) -> str:
    """The shipped referee rule: upgrades on uncertain lines, downgrades on confident ones."""

    out = [_deterministic_summary(cases), ""]
    out.append(
        f"{'panel':<10}{'tol':>6} | {'upgraded':>8}{'right':>6}{'wrong':>6} |"
        f" {'matched':>7}{'caught':>7}{'false':>6}{'missed':>7} | review"
    )
    for name, models in PANELS.items():
        for tolerance in tolerances:
            referee = MatchReferee(
                harness.engine(Purpose.MATCH_REFEREE, models),
                panel=models,
                tolerance_dv=Decimal(tolerance),
            )
            up = up_right = matched = caught = false_alarm = missed = review = 0
            for case in cases:
                if not case.candidates:
                    review += 1
                    continue
                judgement = referee.judge(referee_line(case), case.decision)
                final = judgement.decision
                food = final.candidate.food if final.candidate else None
                if case.decision.status == "matched":
                    matched += 1
                    was_right = case.correct(case.decision.candidate.food)  # type: ignore[union-attr]
                    if final.status != "matched":
                        review += 1
                        if was_right:
                            false_alarm += 1
                        else:
                            caught += 1
                    elif not was_right:
                        missed += 1
                elif final.status == "matched":
                    up += 1
                    up_right += case.correct(food)
                else:
                    review += 1
            out.append(
                f"{name:<10}{tolerance:>6} | {up:>8}{up_right:>6}{up - up_right:>6} |"
                f" {matched:>7}{caught:>7}{false_alarm:>6}{missed:>7} | {review}"
            )
    out.append(
        "\nupgraded: uncertain lines resolved by the panel; caught/false: confident matches sent to"
        " review that were wrong/right; missed: wrong confident matches left in place;"
        " review: lines left for a person (of all gold lines)."
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


# --- hidden ingredients --------------------------------------------------------------------------


def report_hidden_ingredients(harness: Harness) -> str:
    """Per-pair worst-case P(contains) from the shipped check, scored against hand labels."""

    import cookfully.application.hidden_ingredients as hidden
    from uuid import uuid4

    cases = json.loads((RESULTS / "hidden_ingredients_gold.json").read_text("utf-8"))["cases"]
    out = [f"Labelled pairs: {len(cases)} ({sum(c['contains'] for c in cases)} contain the item)", ""]
    out.append(f"{'panel':<10}{'threshold':>10}{'flagged':>9}{'recall':>8}{'precision':>11}{'missed':>8}")
    original = hidden.THRESHOLD
    hidden.THRESHOLD = Decimal(0)  # keep every probability; thresholds are applied below
    try:
        for name, models in PANELS.items():
            engine = harness.engine(Purpose.HIDDEN_INGREDIENTS, models)
            scored: list[tuple[Decimal | None, bool]] = []
            for case in cases:
                line = hidden.HiddenLine(uuid4(), case["line"])
                result = hidden.check_hidden(
                    engine, recipe_title="", lines=[line], avoid=[case["item"]]
                )
                probability = result.flags[0].probability if result.flags else None
                scored.append((probability, case["contains"]))
            positives = sum(1 for _, label in scored if label)
            for threshold in ("0.3", "0.5", "0.7"):
                cut = Decimal(threshold)
                flagged = [(p, label) for p, label in scored if p is not None and p >= cut]
                hits = sum(1 for _, label in flagged if label)
                missed = [c["line"] + " / " + c["item"] for c, (p, label) in zip(cases, scored) if label and (p is None or p < cut)]
                out.append(
                    f"{name:<10}{threshold:>10}{len(flagged):>9}{hits / positives:>8.0%}"
                    f"{(hits / len(flagged) if flagged else 0):>11.0%}{len(missed):>8}"
                )
                if threshold == "0.5" and missed:
                    out.append("            missed at 0.5: " + "; ".join(missed))
    finally:
        hidden.THRESHOLD = original
    return "\n".join(out)


# --- imports ---------------------------------------------------------------------------------------


def _import_guard(harness: Harness, models: tuple[str, ...]) -> Any:
    from cookfully.application.import_decisions import ImportDecisions

    engine = harness.engine(Purpose.IMPORT_LINE_GATE, models)
    # One engine serves all three import purposes with the same panel.
    engine._config = DecisionsConfig(  # noqa: SLF001
        engine.config.api_key,
        engine.config.monthly_cap_usd,
        {purpose: FeatureConfig(True, models) for purpose in Purpose},
    )
    return ImportDecisions(engine)


def report_line_gate(harness: Harness) -> str:
    lines = json.loads((RESULTS / "exp2_dataset.json").read_text("utf-8"))
    real = sum(1 for line in lines if line["label"] == "ingredient")
    junk = len(lines) - real
    out = [f"Lines: {len(lines)} ({real} real ingredients, {junk} junk)", ""]
    out.append(f"{'panel':<10}{'moved':>7}{'junk moved':>12}{'real moved':>12}")
    for name, models in PANELS.items():
        guard = _import_guard(harness, models)
        moved = {line.index for line in guard.gate_lines("", [row["text"] for row in lines])}
        junk_moved = sum(1 for i in moved if lines[i]["label"] != "ingredient")
        real_moved = [lines[i]["text"] for i in moved if lines[i]["label"] == "ingredient"]
        out.append(f"{name:<10}{len(moved):>7}{junk_moved:>7} / {junk:<3}{len(real_moved):>7} / {real}")
        if real_moved:
            out.append("            real lines moved: " + "; ".join(real_moved))
    return "\n".join(out)


def report_import_screen(harness: Harness) -> str:
    pages = json.loads((RESULTS / "import_pages_gold.json").read_text("utf-8"))["pages"]
    out = [f"Pages: {len(pages)}", ""]
    for name, models in PANELS.items():
        guard = _import_guard(harness, models)
        rows = []
        for page in pages:
            result = guard.screen(page["title"], page["ingredients"], page["steps"])
            rows.append((page, result))
        inj = sum(1 for p, r in rows if r.injection == p["injection"])
        clean = sum(1 for p, r in rows if r.clean == p["clean"])
        not_recipe = sum(1 for p, r in rows if r.not_recipe == (p["kind"] in {"article", "other"}))
        out.append(
            f"{name:<10} injection {inj}/{len(rows)}  clean {clean}/{len(rows)}"
            f"  not-a-recipe {not_recipe}/{len(rows)}"
        )
        for page, result in rows:
            out.append(
                f"    {page['id']:<10} inj={result.evidence.get('injection', '-'):<7}"
                f" clean={result.evidence.get('clean', '-'):<7} kind={result.kind}"
                f"{'  <-- miss' if (result.injection != page['injection'] or result.clean != page['clean']) else ''}"
            )
    return "\n".join(out)


def report_cleanup_verifier(harness: Harness) -> str:
    cases = json.loads((RESULTS / "cleanup_verifier_gold.json").read_text("utf-8"))["cases"]
    invented = sum(1 for c in cases if c["invented"])
    out = [f"Cases: {len(cases)} ({invented} invented, {len(cases) - invented} rewordings)", ""]
    for name, models in PANELS.items():
        guard = _import_guard(harness, models)
        caught = false_alarm = 0
        misses = []
        for case in cases:
            flagged = bool(guard.invented(case["source"], [case["cleaned"]]))
            if flagged and case["invented"]:
                caught += 1
            elif flagged:
                false_alarm += 1
                misses.append("false alarm: " + case["cleaned"])
            elif case["invented"]:
                misses.append("missed: " + case["cleaned"])
        out.append(f"{name:<10} caught {caught}/{invented}  false alarms {false_alarm}")
        if misses:
            out.append("            " + "; ".join(misses))
    return "\n".join(out)


# --- facets ----------------------------------------------------------------------------------------


def report_facets(harness: Harness) -> str:
    """Facets for the 50 corpus recipes (ingredients only), for a manual spot-check."""

    from cookfully.application.recipe_facets import facet_ask
    from cookfully.domain.recipe_facets import interpret

    derived = json.loads((CORPUS / "derived-inputs.json").read_text("utf-8"))
    manifest = json.loads((CORPUS / "manifest.json").read_text("utf-8"))
    titles = {case["id"]: case["slug"].replace("-", " ") for case in manifest["cases"]}
    engine = harness.engine(Purpose.RECIPE_FACETS, PANELS["jev+clef"])
    cases = derived["cases"]
    lines_by_case = [[i["originalText"] for i in case["ingredients"]] for case in cases]
    asks = [
        facet_ask(titles.get(case["caseId"], ""), lines, [])
        for case, lines in zip(cases, lines_by_case, strict=True)
    ]
    out = []
    counts: Counter[str] = Counter()
    for case, lines, answers in zip(cases, lines_by_case, engine.ask(asks), strict=True):
        tags = interpret(answers, lines)
        counts.update(tag.key.split(":")[0] for tag in tags)
        rendered = ", ".join(
            f"{tag.key}{'' if tag.confident else '?'}" for tag in tags
        )
        out.append(f"{titles.get(case['caseId'], case['caseId'])[:38]:<38} {rendered}")
    out.append("")
    out.append("tag counts: " + ", ".join(f"{k}={v}" for k, v in counts.most_common()))
    return "\n".join(out)


# --- food labels -----------------------------------------------------------------------------------

_STATE_WORDS = {
    "raw": ("raw",),
    "cooked": ("cooked", "boiled", "roasted", "baked", "fried", "grilled", "steamed", "braised", "broiled"),
    "canned": ("canned",),
    "frozen": ("frozen",),
    "dried": ("dried", "dehydrated"),
}


def _expected_state(description: str) -> str | None:
    words = set(description.lower().replace(",", " ").split())
    found = [state for state, tokens in _STATE_WORDS.items() if words & set(tokens)]
    return found[0] if len(found) == 1 else None


def _label_foods(harness: Harness, foods: list[FoodReference]) -> dict[Any, Any]:
    from cookfully.application.food_labels import label_ask, labels_from
    from cookfully.domain.food_labels import FoodLabels

    engine = harness.engine(Purpose.FOOD_LABELS, PANELS["jev+clef"])
    result: dict[Any, Any] = {}
    for start in range(0, len(foods), 50):
        batch = foods[start : start + 50]
        for food, answers in zip(batch, engine.ask([label_ask(f) for f in batch]), strict=True):
            labels = labels_from(answers)
            if labels is not None:
                result[food.id] = FoodLabels.from_json(labels)
    return result


def report_food_labels(harness: Harness, usda_dir: Path) -> str:
    foods = sorted(load_foods(usda_dir), key=lambda food: food.external_id)
    by_state: dict[str, list[FoodReference]] = defaultdict(list)
    for food in foods:
        state = _expected_state(food.description)
        if state and len(by_state[state]) < 24:
            by_state[state].append(food)
    sample = [food for group in by_state.values() for food in group]
    labels = _label_foods(harness, sample)
    out = [f"Foods with one explicit state word in the USDA description: {len(sample)}", ""]
    total = right = 0
    confusions: Counter[str] = Counter()
    for food in sample:
        expected = _expected_state(food.description)
        got = labels.get(food.id)
        total += 1
        if got is not None and got.state == expected:
            right += 1
        else:
            confusions[f"{expected}->{got.state if got else 'none'}"] += 1
    out.append(f"state matches the description word: {right}/{total} ({right / total:.0%})")
    out.append("mismatches: " + ", ".join(f"{k} x{v}" for k, v in confusions.most_common()))
    return "\n".join(out)


def report_match_labels(harness: Harness, usda_dir: Path) -> str:
    """Deterministic matching on the gold set without and with stored food labels."""

    foods = load_foods(usda_dir)
    gold = gold_labels()
    lines = {line.idx: line for line in corpus_lines()}
    plain = FoodMatcher(StubNutritionRepository(foods), candidate_pool_limit=256)  # type: ignore[arg-type]
    heads: dict[Any, FoodReference] = {}
    for idx in gold:
        for candidate in plain.candidates(lines[idx].food_name, limit=20):
            heads[candidate.food.id] = candidate.food
    labels = _label_foods(harness, list(heads.values()))
    labelled = FoodMatcher(
        StubNutritionRepository(foods),  # type: ignore[arg-type]
        candidate_pool_limit=256,
        labels_for=lambda batch: {food.id: labels[food.id] for food in batch if food.id in labels},
    )
    out = [f"Candidate foods labelled: {len(labels)} of {len(heads)}", ""]
    for name, matcher in (("without labels", plain), ("with labels", labelled)):
        cases = [
            MatchCase(lines[idx], label, matcher.decide(lines[idx].food_name))
            for idx, label in sorted(gold.items())
        ]
        out.append(f"{name}:")
        out.append(_deterministic_summary(cases))
        top_right = sum(
            1 for case in cases if case.candidates and case.correct(case.candidates[0].food)
        )
        out.append(f"  top candidate correct (any status): {top_right}/{len(cases)}")
    return "\n".join(out)


# --- entry point ---------------------------------------------------------------------------------

Evaluator = Callable[[Harness, argparse.Namespace], str]


def _match_referee(harness: Harness, args: argparse.Namespace) -> str:
    return report_match_referee(harness, match_cases(args.usda_dir), args.tolerance)


def _hidden_ingredients(harness: Harness, args: argparse.Namespace) -> str:
    del args
    return report_hidden_ingredients(harness)


EVALUATORS: dict[str, Evaluator] = {
    "match-referee": _match_referee,
    "hidden-ingredients": _hidden_ingredients,
    "line-gate": lambda harness, _args: report_line_gate(harness),
    "import-screen": lambda harness, _args: report_import_screen(harness),
    "cleanup-verifier": lambda harness, _args: report_cleanup_verifier(harness),
    "facets": lambda harness, _args: report_facets(harness),
    "food-labels": lambda harness, args: report_food_labels(harness, args.usda_dir),
    "match-labels": lambda harness, args: report_match_labels(harness, args.usda_dir),
}


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
