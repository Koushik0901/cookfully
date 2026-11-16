"""Experiment 1d: score decision-model food matching against the frozen blind gold labels.

All counts are weighted from the 140-line stratified sample to the 531-line corpus.
"wrong auto" = a line resolved without review whose chosen food is not gold-acceptable, or any
auto-resolution of a gold non-food / no-answer line.

Policies compared (review queue = lines a person must look at):
  baseline_fixed   deterministic matcher (with the identity-fallback patch) resolves `matched`
  model_only(t)    model's top option auto-resolves when p >= t and it is not `none`
  tail_only(t)     matcher keeps its `matched` decisions; model only tries the review tail
  veto(t)          like tail_only, but a confident model disagreement sends a `matched` line to review
Pure stdlib. Usage: python exp1_eval_models.py <workdir>
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

WORK = Path(sys.argv[1])
rows = {r["idx"]: r for r in (json.loads(x) for x in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines())}
gold = {int(k): v for k, v in json.loads((WORK / "gold_labels.json").read_text("utf-8")).items()}
out = json.loads((WORK / "exp1_model_outputs.json").read_text("utf-8"))
N_RECIPES = 50


def is_tie(cond):  # type: ignore[no-untyped-def]
    c = cond["candidates"]
    return len(c) >= 2 and abs(c[0]["score"] - c[1]["score"]) < 1e-9


def stratum(r):  # type: ignore[no-untyped-def]
    a, f = r["asis"], r["fixed"]
    if a["status"] == "unmatched" and f["status"] != "unmatched":
        return "recovered"
    if f["status"] == "unmatched":
        return "unmatched"
    if f["status"] == "matched":
        return "matched"
    return "tie" if is_tie(f) else "amb_other"


pop = Counter(stratum(r) for r in rows.values())
samp = Counter(v["stratum"] for v in gold.values())
W = {s: pop[s] / samp[s] for s in samp}
TOTAL = sum(W[v["stratum"]] for v in gold.values())  # == 531


def correct(idx: int, fdc: str | None) -> bool:
    g = gold[idx]
    return fdc is not None and g["kind"] == "food" and fdc in set(g["acceptable"])


def model_top(model: str, idx: int):  # type: ignore[no-untyped-def]
    """(fdcId or None for 'none'/unanswered, probability of that top option)"""
    o = out[model].get(str(idx), {})
    probs = o.get("match")
    if not probs:
        return None, 0.0
    key = max(probs, key=probs.get)
    return (None if key == "none" else o["options"].get(key)), probs[key]


def evaluate(decide):  # type: ignore[no-untyped-def]
    """decide(idx) -> fdcId or None (None = send to review). Returns weighted (auto, wrong, review)."""
    auto = wrong = 0.0
    for idx, v in gold.items():
        w = W[v["stratum"]]
        d = decide(idx)
        if d is not None:
            auto += w
            wrong += w * (not correct(idx, d))
    return auto, wrong, TOTAL - auto


def baseline(idx):  # type: ignore[no-untyped-def]
    f = rows[idx]["fixed"]
    return f["decidedFdcId"] if f["status"] == "matched" else None


def baseline_asis(idx):  # type: ignore[no-untyped-def]
    f = rows[idx]["asis"]
    return f["decidedFdcId"] if f["status"] == "matched" else None


def fmt(t):  # type: ignore[no-untyped-def]
    auto, wrong, review = t
    return (f"auto={auto:5.0f} ({auto / TOTAL:5.1%}) wrong_auto={wrong:4.1f} "
            f"({(wrong / auto if auto else 0):5.1%} of auto) review={review:5.0f} ({review / N_RECIPES:4.1f}/recipe)")


print(f"population={TOTAL:.0f} lines, {N_RECIPES} recipes\n")
print("== deterministic baselines ==")
print("  as-is          ", fmt(evaluate(baseline_asis)))
print("  fixed          ", fmt(evaluate(baseline)))
summary: dict = {}  # type: ignore[type-arg]

# --- ranking quality: top-1 on food lines (no thresholds) ----------------------------------------
food_idx = [i for i, v in gold.items() if v["kind"] == "food"]
fw = sum(W[gold[i]["stratum"]] for i in food_idx)
def acc(fn):  # type: ignore[no-untyped-def]
    return sum(W[gold[i]["stratum"]] * correct(i, fn(i)) for i in food_idx) / fw
print("\n== top-1 accuracy on gold food lines (weighted; 'none' counts as wrong) ==")
print(f"  as-is  top candidate : {acc(lambda i: (rows[i]['asis']['candidates'] or [{'fdcId': None}])[0]['fdcId']):.1%}")
print(f"  fixed  top candidate : {acc(lambda i: (rows[i]['fixed']['candidates'] or [{'fdcId': None}])[0]['fdcId']):.1%}")
for m in out:
    top1 = acc(lambda i, m=m: model_top(m, i)[0])
    # tail only (lines the fixed matcher did not auto-match)
    tail = [i for i in food_idx if rows[i]["fixed"]["status"] != "matched"]
    tw = sum(W[gold[i]["stratum"]] for i in tail)
    tacc = sum(W[gold[i]["stratum"]] * correct(i, model_top(m, i)[0]) for i in tail) / tw
    fixed_tail = sum(W[gold[i]["stratum"]] * correct(i, (rows[i]["fixed"]["candidates"] or [{"fdcId": None}])[0]["fdcId"]) for i in tail) / tw
    summary[m] = {"top1": top1, "tail_top1": tacc, "fixed_tail_top1": fixed_tail}
    print(f"  {m:42s}: {top1:.1%}   | on review-tail lines only: model {tacc:.1%} vs fixed-top {fixed_tail:.1%}")

# --- threshold sweeps ---------------------------------------------------------------------------
THRESH = [0.5, 0.7, 0.8, 0.9, 0.95, 0.98]
for m in out:
    print(f"\n== {m} ==")
    def model_only(idx, t):  # type: ignore[no-untyped-def]
        d, p = model_top(m, idx)
        return d if d is not None and p >= t else None
    def tail_only(idx, t):  # type: ignore[no-untyped-def]
        b = baseline(idx)
        return b if b is not None else model_only(idx, t)
    def veto(idx, t):  # type: ignore[no-untyped-def]
        b = baseline(idx)
        if b is None:
            return model_only(idx, t)
        d, p = model_top(m, idx)
        return None if (d != b and p >= t) else b
    for t in THRESH:
        print(f"  t={t:4.2f} model_only {fmt(evaluate(lambda i: model_only(i, t)))}")
    for t in (0.8, 0.9, 0.95):
        print(f"  t={t:4.2f} tail_only  {fmt(evaluate(lambda i: tail_only(i, t)))}")
    for t in (0.8, 0.9, 0.95):
        print(f"  t={t:4.2f} veto       {fmt(evaluate(lambda i: veto(i, t)))}")

# --- calibration of the top option (food lines + non-food lines together) ----------------------
print("\n== calibration: P(top option correct) by confidence bin (weighted) ==")
bins = [(0, .5), (.5, .8), (.8, .9), (.9, .95), (.95, .99), (.99, 1.01)]
for m in out:
    cells = []
    ece = 0.0
    for lo, hi in bins:
        n = c = ps = 0.0
        for idx, v in gold.items():
            d, p = model_top(m, idx)
            if d is None or not (lo <= p < hi):
                continue
            w = W[v["stratum"]]
            n += w; c += w * correct(idx, d); ps += w * p
        cells.append(f"{lo:.2f}-{min(hi, 1):.2f}: {c / n:.0%} (n={n:.0f})" if n else f"{lo:.2f}-{min(hi, 1):.2f}: -")
        ece += (n / TOTAL) * abs(c / n - ps / n) if n else 0
    print(f"  {m:42s} ECE={ece:.3f} | " + " | ".join(cells))

# --- non-food detection (is_food_ingredient) ---------------------------------------------------
print("\n== is_food_ingredient (noul) on the labelled sample ==")
pos = [i for i, v in gold.items() if v["kind"] in ("not_food", "multi")]
neg = [i for i, v in gold.items() if v["kind"] in ("food", "none")]
print(f"  positives (not a single food line): {len(pos)} | negatives (real foods): {len(neg)}")
for m in out:
    def p_food(i):  # type: ignore[no-untyped-def]
        return out[m][str(i)].get("food_p")
    ps = [(1 - p_food(i), 1) for i in pos if p_food(i) is not None] + [(1 - p_food(i), 0) for i in neg if p_food(i) is not None]
    # AUROC by pairwise comparison
    P = [s for s, y in ps if y]; Nn = [s for s, y in ps if not y]
    auroc = sum((a > b) + 0.5 * (a == b) for a in P for b in Nn) / (len(P) * len(Nn))
    row = []
    for t in (0.5, 0.8, 0.9):
        flagged = lambda i, t=t: (1 - p_food(i)) >= t
        tp = sum(flagged(i) for i in pos); fp = sum(flagged(i) for i in neg)
        row.append(f"flag@{t}: recall {tp}/{len(pos)}, false-flags {fp}/{len(neg)}")
    print(f"  {m:42s} AUROC={auroc:.3f} | " + " | ".join(row))

(WORK / "exp1_results.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
