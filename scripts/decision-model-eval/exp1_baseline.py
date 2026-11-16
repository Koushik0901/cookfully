"""Experiment 1a: run the real deterministic FoodMatcher over the 50-recipe corpus.

Three deterministic conditions are recorded for every ingredient line:

* ``asis``    - the app's matcher exactly as shipped.
* ``fixed``   - harness-only patch: an ``identity_conflict`` is ignored when either side's
                identity is a last-token *guess* (not from the curated lexicon/aliases).
                Without this, USDA names such as "Celery, raw" get identity "raw" and are
                hard-rejected. This is NOT applied to the app; it keeps the model comparison
                honest (otherwise models would just beat a broken baseline).
* ``lenient`` - same shortlist/scoring but semantic CONTRADICTORY results are kept as
                REVIEW, used only to build a wide candidate set for the recall ceiling.

The corpus's pinned FDC id is algorithmically derived (scripts/build-nutrition-corpus-inputs.py);
it is a reference point, not human gold.

Run (from repo root):
    uv run --directory backend --frozen python ../scripts/decision-model-eval/exp1_baseline.py \
        --usda-dir <dir containing usda-foundation/ and usda-srlegacy/> --out <workdir>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from usda_pool import StubNutritionRepository, load_pool  # noqa: E402

from cookfully.domain import food_semantics as fs  # noqa: E402
from cookfully.domain.food_semantics import Compatibility, CompatibilityResult  # noqa: E402
from cookfully.domain.ingredient_nutrition import matching  # noqa: E402
from cookfully.domain.ingredient_nutrition.matching import FoodMatcher  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DERIVED = ROOT / "backend" / "tests" / "fixtures" / "nutrition-corpus" / "derived-inputs.json"
TOP_K = 8
_ORIGINAL_COMPARE = fs.compare_compatibility
_TRUSTED_IDENTITIES = set(fs._CATEGORY_BY_IDENTITY) | set(fs._IDENTITY_ALIASES.values())
_HARD = ("identity_conflict", "category_conflict", "part_conflict", "state_conflict", "form_conflict")


def _fixed_compare(query, candidate):  # type: ignore[no-untyped-def]
    result = _ORIGINAL_COMPARE(query, candidate)
    if result.compatibility is not Compatibility.CONTRADICTORY:
        return result
    if "identity_conflict" not in result.reasons:
        return result
    trusted = (
        query.canonical_identity in _TRUSTED_IDENTITIES
        and candidate.canonical_identity in _TRUSTED_IDENTITIES
    )
    if trusted:
        return result
    remaining = tuple(r for r in result.reasons if r != "identity_conflict")
    if any(r in _HARD for r in remaining):
        return CompatibilityResult(Compatibility.CONTRADICTORY, remaining)
    return CompatibilityResult(Compatibility.REVIEW if remaining else Compatibility.COMPATIBLE, remaining)


def _lenient_compare(query, candidate):  # type: ignore[no-untyped-def]
    result = _ORIGINAL_COMPARE(query, candidate)
    if result.compatibility is Compatibility.CONTRADICTORY:
        return CompatibilityResult(Compatibility.REVIEW, result.reasons)
    return result


@contextmanager
def patched(fn):  # type: ignore[no-untyped-def]
    matching.compare_compatibility = fn
    try:
        yield
    finally:
        matching.compare_compatibility = _ORIGINAL_COMPARE


def serialise(cands: tuple) -> list[dict]:  # type: ignore[type-arg]
    return [
        {
            "fdcId": c.food.external_id,
            "description": c.food.description,
            "dataType": c.food.data_type,
            "foodCategory": c.food.food_category,
            "score": float(c.score),
            "compat": c.compatibility.value,
        }
        for c in cands
    ]


def run_condition(matcher: FoodMatcher, name: str) -> dict:  # type: ignore[type-arg]
    decision = matcher.decide(name)
    return {
        "status": decision.status,
        "method": decision.method,
        "decidedFdcId": decision.candidate.food.external_id if decision.candidate else None,
        "candidates": serialise(matcher.candidates(name, limit=TOP_K)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--usda-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    pool = load_pool(
        args.usda_dir / "usda-foundation" / "foundation.zip",
        args.usda_dir / "usda-srlegacy" / "srlegacy.zip",
    )
    print(f"pool: {len(pool)} foods", flush=True)
    matcher = FoodMatcher(StubNutritionRepository(pool), candidate_pool_limit=256)  # type: ignore[arg-type]
    derived = json.loads(DERIVED.read_text(encoding="utf-8"))
    pinned_desc = {food["fdcId"]: food["description"] for food in derived["foods"]}

    rows = []
    started = time.perf_counter()
    for case in derived["cases"]:
        for ing in case["ingredients"]:
            name = ing["parsedFoodName"] or ing["originalText"]
            asis = run_condition(matcher, name)
            with patched(_fixed_compare):
                fixed = run_condition(matcher, name)
            with patched(_lenient_compare):
                lenient = serialise(matcher.candidates(name, limit=TOP_K))
            pinned = ing["foodFdcId"]
            rows.append(
                {
                    "idx": len(rows),
                    "caseId": case["caseId"],
                    "position": ing["position"],
                    "originalText": ing["originalText"],
                    "foodName": name,
                    "grams": ing.get("grams"),
                    "asis": asis,
                    "fixed": fixed,
                    "lenientCandidates": lenient,
                    "pinnedFdcId": pinned,
                    "pinnedDescription": pinned_desc.get(pinned),
                    "optional": ing.get("optional", False),
                }
            )
    elapsed = time.perf_counter() - started
    out = args.out / "baseline_matches.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    n = len(rows)
    print(f"lines={n} elapsed={elapsed:.1f}s -> {out}")
    for cond in ("asis", "fixed"):
        status = Counter(r[cond]["status"] for r in rows)
        matched = [r for r in rows if r[cond]["status"] == "matched"]
        agree = sum(r[cond]["decidedFdcId"] == r["pinnedFdcId"] for r in matched)
        zero = sum(not r[cond]["candidates"] for r in rows)
        print(
            f"[{cond}] status={dict(status)} | auto-matched agree w/ pinned {agree}/{len(matched)}"
            f" | lines with zero candidates: {zero}"
        )


if __name__ == "__main__":
    main()
