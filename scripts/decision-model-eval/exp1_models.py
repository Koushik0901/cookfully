"""Experiment 1c: ask decision models to pick the USDA food for each gold-labelled line.

Two typed questions per line, asked in separate requests:
  match            choice over candidate foods (+ "none")
  is_food_ingredient  noul: is this line a real food ingredient at all? (import-cleanup signal)
The candidate set is what the app could show: fixed-baseline top-8, then lenient, then as-is
candidates (de-duplicated, max 14, original ranking order). The corpus's pinned id is NOT injected.
Pure stdlib. Usage:
    COOKFULLY_ENV_FILE=<.env> python exp1_models.py <workdir> [model ...]
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dm_client import BudgetExceeded, DecisionClient, choice_probs, noul_prob  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(sys.argv[1])
MODELS = sys.argv[2:] or [
    "typesafe/jev-1.14",
    "cloudflare/clef",
    "cloudflare/clef-flash",
    "liquid/d1",
    "jaredpalmer/kev-4b",
    "perplexity/pplx-decider-flash-v1.3:free",
    "openai/gpt-6-luna-decisions",
]
MAX_OPTIONS = 14

manifest = json.loads((ROOT / "backend/tests/fixtures/nutrition-corpus/manifest.json").read_text("utf-8"))
title_of = {c["id"]: c["slug"].replace("-", " ") for c in manifest["cases"]}
rows = {
    r["idx"]: r
    for r in (json.loads(x) for x in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines())
}
gold = json.loads((WORK / "gold_labels.json").read_text("utf-8"))

MATCH_INSTRUCTIONS = (
    "Which USDA FoodData Central entry best represents this recipe ingredient for nutrition lookup? "
    "Match the food and the state implied by the line (raw for fresh produce and meat, dry for grains "
    "and pasta unless the line says cooked, drained for canned foods). Prefer plain generic entries over "
    "flavored, processed, branded or different-part variants. Answer none if no entry is an acceptable "
    "match or the line is not a food ingredient."
)
FOOD_INSTRUCTIONS = (
    "Does this ingredient line name a real food that can be looked up in a nutrition database? Answer no "
    "for kitchen equipment, bare quantities or units, preparation-only fragments (such as chopped, divided, "
    "melted), section headings and cooking instructions."
)


def options_for(row: dict) -> list[dict]:  # type: ignore[type-arg]
    seen: dict[str, dict] = {}  # type: ignore[type-arg]
    for cand in row["fixed"]["candidates"] + row["lenientCandidates"] + row["asis"]["candidates"]:
        seen.setdefault(cand["fdcId"], cand)
    return list(seen.values())[:MAX_OPTIONS]


def run_one(client: DecisionClient, model: str, idx: int) -> tuple[str, int, dict]:  # type: ignore[type-arg]
    row = rows[idx]
    state = {
        "recipe": title_of[row["caseId"]],
        "ingredient_line": row["originalText"],
        "parsed_food_name": row["foodName"],
    }
    opts = options_for(row)
    out: dict = {"options": {f"c{i + 1}": o["fdcId"] for i, o in enumerate(opts)}}  # type: ignore[type-arg]
    if opts:
        criteria = {
            f"c{i + 1}": o["description"] + (f" [{o['foodCategory']}]" if o.get("foodCategory") else "")
            for i, o in enumerate(opts)
        }
        criteria["none"] = "None of the listed entries is an acceptable match, or this line is not a food ingredient."
        resp = client.decide(model, state, {"match": {"type": "choice", "instructions": MATCH_INSTRUCTIONS, "criteria": criteria}})
        out["match"] = choice_probs(resp, "match") if "error" not in resp else None
        out["match_error"] = resp.get("error")
        out["served_by"] = resp.get("model")
    resp2 = client.decide(
        model,
        state,
        {
            "is_food_ingredient": {
                "type": "noul",
                "instructions": FOOD_INSTRUCTIONS,
                "criteria": {"true": "A real food ingredient.", "false": "Not a food ingredient."},
            }
        },
    )
    out["food_p"] = noul_prob(resp2, "is_food_ingredient") if "error" not in resp2 else None
    out["food_error"] = resp2.get("error")
    return model, idx, out


def main() -> None:
    client = DecisionClient(WORK)
    results: dict[str, dict[str, dict]] = {m: {} for m in MODELS}  # type: ignore[type-arg]
    jobs = [(m, int(i)) for m in MODELS for i in gold]
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for model, idx, out in pool.map(lambda j: run_one(client, *j), jobs):
                results[model][str(idx)] = out
    except BudgetExceeded as exc:
        print("STOPPED:", exc)
    (WORK / "exp1_model_outputs.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    errs = {m: sum(1 for v in r.values() if v.get("match_error") or v.get("food_error")) for m, r in results.items()}
    print("done.", client.summary(), "| lines with errors per model:", errs)


if __name__ == "__main__":
    main()
