"""Experiment 1b: score the deterministic baselines against the frozen blind gold labels.

Reports, per condition (as-is / fixed):
* candidate recall  - gold-acceptable food present in top-1 / top-3 / top-8 candidates
                      (the ceiling for any re-ranker: a decision model can only pick what it is shown)
* auto-match precision - of lines the matcher resolves without review, how many are acceptable
* review queue - lines needing human input
Numbers are weighted back to the full 531-line corpus using the stratified-sample weights.
Pure stdlib. Usage: python exp1_eval_baseline.py <workdir>
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

WORK = Path(sys.argv[1])
rows = [json.loads(x) for x in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines()]
gold = json.loads((WORK / "gold_labels.json").read_text("utf-8"))
by_idx = {r["idx"]: r for r in rows}


def is_tie(cond: dict) -> bool:  # type: ignore[type-arg]
    c = cond["candidates"]
    return len(c) >= 2 and abs(c[0]["score"] - c[1]["score"]) < 1e-9


def stratum(row: dict) -> str:  # type: ignore[type-arg]
    asis, fixed = row["asis"], row["fixed"]
    if asis["status"] == "unmatched" and fixed["status"] != "unmatched":
        return "recovered"
    if fixed["status"] == "unmatched":
        return "unmatched"
    if fixed["status"] == "matched":
        return "matched"
    return "tie" if is_tie(fixed) else "amb_other"


pop = Counter(stratum(r) for r in rows)
samp = Counter(v["stratum"] for v in gold.values())
weight = {s: pop[s] / samp[s] for s in samp}


def wsum(items: list[tuple[str, bool]]) -> float:
    return sum(weight[s] for s, ok in items if ok)


def report(cond: str) -> dict:  # type: ignore[type-arg]
    food = [(v["stratum"], by_idx[int(i)][cond], set(v["acceptable"])) for i, v in gold.items() if v["kind"] == "food"]
    nonfood = [(v["stratum"], by_idx[int(i)][cond]) for i, v in gold.items() if v["kind"] != "food"]
    n_food_w = sum(weight[s] for s, _, _ in food)
    rec = {}
    for k in (1, 3, 8):
        rec[k] = wsum([(s, bool({c["fdcId"] for c in cd["candidates"][:k]} & acc)) for s, cd, acc in food]) / n_food_w
    matched = [(s, cd, acc) for s, cd, acc in food if cd["status"] == "matched"]
    nm_matched = [(s, cd) for s, cd in nonfood if cd["status"] == "matched"]
    ok = wsum([(s, cd["decidedFdcId"] in acc) for s, cd, acc in matched])
    wrong_food = wsum([(s, cd["decidedFdcId"] not in acc) for s, cd, acc in matched])
    wrong_nonfood = wsum([(s, True) for s, cd in nm_matched])
    auto = ok + wrong_food + wrong_nonfood
    pop_auto = sum(1 for r in rows if r[cond]["status"] == "matched")
    return {
        "recall@1": rec[1], "recall@3": rec[3], "recall@8": rec[8],
        "auto_matched_lines(pop)": pop_auto,
        "auto_precision(est)": ok / auto if auto else float("nan"),
        "auto_wrong_est_lines": wrong_food + wrong_nonfood,
        "review_queue_lines(pop)": len(rows) - pop_auto,
        "status": dict(Counter(r[cond]["status"] for r in rows)),
    }


print("population strata:", dict(pop), "| sample:", dict(samp))
print("gold kinds (sample):", dict(Counter(v["kind"] for v in gold.values())))
est_nonfood = sum(weight[v["stratum"]] for v in gold.values() if v["kind"] != "food")
print(f"estimated non-food/no-answer lines in population: {est_nonfood:.0f} of {len(rows)} ({est_nonfood/len(rows):.1%})\n")
for cond in ("asis", "fixed"):
    r = report(cond)
    print(f"== {cond} ==")
    for k, v in r.items():
        print(f"  {k:28s} {v:.3f}" if isinstance(v, float) else f"  {k:28s} {v}")
# within-sample detail on how often the model-visible candidate set contains an acceptable food
print("\nrecall@8 on union(asis,fixed,lenient) candidate set (what models are shown):")
food_items = [(v["stratum"], i, set(v["acceptable"])) for i, v in gold.items() if v["kind"] == "food"]
tot = sum(weight[s] for s, _, _ in food_items)
def union_ids(r):  # type: ignore[no-untyped-def]
    return {c["fdcId"] for c in r["fixed"]["candidates"] + r["lenientCandidates"] + r["asis"]["candidates"]}
hit = sum(weight[s] for s, i, acc in food_items if union_ids(by_idx[int(i)]) & acc)
print(f"  {hit/tot:.3f} (estimated, food lines)")
by_s = defaultdict(lambda: [0, 0])
for s, i, acc in food_items:
    by_s[s][1] += 1
    by_s[s][0] += bool(union_ids(by_idx[int(i)]) & acc)
print("  raw sample hit by stratum:", {s: f"{a}/{b}" for s, (a, b) in by_s.items()})
