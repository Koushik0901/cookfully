"""Experiment 1f (model calls): all 531 corpus lines x selected decision models.

Per line, two typed questions (separate requests, cached):
  match      choice over candidate foods (+ none)               [same prompt as exp1_models.py]
  calories   score on 4 ordered buckets: how many calories does this line add to the whole
             recipe? The model sees only the line text and recipe title, never USDA data.
Pure stdlib. Usage:
    COOKFULLY_ENV_FILE=<.env> python exp1f_models.py <workdir> [model ...]
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dm_client import BudgetExceeded, DecisionClient, choice_probs  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(sys.argv[1])
MODELS = sys.argv[2:] or [
    "typesafe/jev-1.14",
    "cloudflare/clef",
    "openai/gpt-6-luna-decisions",
    "perplexity/pplx-decider-flash-v1.3:free",
]
MAX_OPTIONS = 14
manifest = json.loads((ROOT / "backend/tests/fixtures/nutrition-corpus/manifest.json").read_text("utf-8"))
title_of = {c["id"]: c["slug"].replace("-", " ") for c in manifest["cases"]}
rows = [json.loads(x) for x in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines()]

MATCH_INSTRUCTIONS = (
    "Which USDA FoodData Central entry best represents this recipe ingredient for nutrition lookup? "
    "Match the food and the state implied by the line (raw for fresh produce and meat, dry for grains "
    "and pasta unless the line says cooked, drained for canned foods). Prefer plain generic entries over "
    "flavored, processed, branded or different-part variants. Answer none if no entry is an acceptable "
    "match or the line is not a food ingredient."
)
CAL_INSTRUCTIONS = (
    "How many calories does this ingredient line add to the whole recipe, counting the quantity as written? "
    "If the line is not a food ingredient, choose the negligible bucket."
)
CAL_CRITERIA = [
    "Negligible: under 10 kcal (salt, pepper, herbs, most spices, citrus zest, a squeeze of citrus juice, water, garnish, cooking spray, equipment, fragments)",
    "Small: 10 to 50 kcal",
    "Moderate: 50 to 200 kcal",
    "Large: over 200 kcal (oils, butter, flour, rice, pasta, meat, cheese, nuts, sugar in typical amounts)",
]


def options_for(row: dict) -> list[dict]:  # type: ignore[type-arg]
    seen: dict[str, dict] = {}  # type: ignore[type-arg]
    for cand in row["fixed"]["candidates"] + row["lenientCandidates"] + row["asis"]["candidates"]:
        seen.setdefault(cand["fdcId"], cand)
    return list(seen.values())[:MAX_OPTIONS]


def run_one(client: DecisionClient, model: str, row: dict) -> tuple[str, int, dict]:  # type: ignore[type-arg]
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
    resp2 = client.decide(model, state, {"calories": {"type": "score", "instructions": CAL_INSTRUCTIONS, "criteria": CAL_CRITERIA}})
    ans = (resp2.get("answers") or {}).get("calories") if "error" not in resp2 else None
    out["cal_probs"] = ans.get("probabilities") if ans else None
    out["cal_score"] = ans.get("score") if ans else None
    out["cal_error"] = resp2.get("error")
    return model, row["idx"], out


def main() -> None:
    client = DecisionClient(WORK)
    results: dict[str, dict[str, dict]] = {m: {} for m in MODELS}  # type: ignore[type-arg]
    jobs = [(m, r) for m in MODELS for r in rows]
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for model, idx, out in pool.map(lambda j: run_one(client, *j), jobs):
                results[model][str(idx)] = out
    except BudgetExceeded as exc:
        print("STOPPED:", exc)
    (WORK / "exp1f_model_outputs.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    errs = {m: sum(1 for v in r.values() if v.get("match_error") or v.get("cal_error")) for m, r in results.items()}
    print("done.", client.summary(), "| lines with errors per model:", errs)


if __name__ == "__main__":
    main()
