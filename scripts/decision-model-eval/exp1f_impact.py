"""Experiment 1g: nutritional-impact-aware matching ("butter matters, lime juice doesn't").

Uses grams-per-line from the corpus and USDA energy per food, so everything is in kcal.

A. Materiality: how calories distribute across lines (reference = corpus-pinned food).
B. Can a decision model predict a line's calorie bucket from text alone? (score question)
C. Impact-aware triage: auto-resolve when EXPECTED kcal error from the model's own probability
   distribution is small, instead of when top-option confidence is high. Scored on the frozen
   gold sample (kcal error vs gold-best food), weighted to the 531 lines.
D. End-to-end per-recipe kcal vs the corpus's PUBLISHED values (independent of my labels).
E. Nutritionally-equivalent ties (deterministic, no model): tied top candidates with tiny kcal spread.
Pure stdlib. Usage: python exp1f_impact.py <workdir> <usda-dir> <repo-root>
"""

from __future__ import annotations

import json
import re
import statistics
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

WORK, USDA, REPO = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
rows = {r["idx"]: r for r in (json.loads(x) for x in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines())}
gold = {int(k): v for k, v in json.loads((WORK / "gold_labels.json").read_text("utf-8")).items()}
out1f = json.loads((WORK / "exp1f_model_outputs.json").read_text("utf-8"))
derived = json.loads((REPO / "backend/tests/fixtures/nutrition-corpus/derived-inputs.json").read_text("utf-8"))
manifest = json.loads((REPO / "backend/tests/fixtures/nutrition-corpus/manifest.json").read_text("utf-8"))

# ---------------------------------------------------------------- USDA energy per 100 g
KCAL: dict[str, float] = {}
for path in (USDA / "usda-foundation/foundation.zip", USDA / "usda-srlegacy/srlegacy.zip"):
    with zipfile.ZipFile(path) as z:
        raw = json.loads(z.read(z.namelist()[0]))
    for food in next(v for v in raw.values() if isinstance(v, list)):
        if not food:
            continue
        nut = {n["nutrient"]["id"]: n.get("amount") for n in food.get("foodNutrients", []) if n.get("nutrient")}
        e = nut.get(1008) or nut.get(2047) or nut.get(2048)
        if e is None:
            p, c, f = (nut.get(1003) or 0), (nut.get(1005) or 0), (nut.get(1004) or 0)
            e = 4 * p + 4 * c + 9 * f
        KCAL[str(food["fdcId"])] = float(e)


def kc(fdc: str | None) -> float:
    return KCAL.get(fdc, 0.0) if fdc else 0.0  # none / unresolved contributes nothing


GRAMS = {r["idx"]: float(derived_ing["grams"]) for r in rows.values()
         for derived_ing in [next(i for c in derived["cases"] if c["caseId"] == r["caseId"] for i in c["ingredients"] if i["position"] == r["position"])]}


def line_kcal(idx: int, fdc: str | None) -> float:
    return GRAMS[idx] * kc(fdc) / 100.0


# ---------------------------------------------------------------- sample weights (as in exp1_eval)
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

# ================================================================ A. materiality
print("=== A. Where do the calories live? (531 lines, kcal of the line as written, reference = pinned food) ===")
BUCKETS = [("negligible <10", 0, 10), ("small 10-50", 10, 50), ("moderate 50-200", 50, 200), ("large >200", 200, 1e9)]


def bucket(k: float) -> int:
    return next(i for i, (_, lo, hi) in enumerate(BUCKETS) if lo <= k < hi)


truth_kcal = {i: line_kcal(i, rows[i]["pinnedFdcId"]) for i in rows}
tot = sum(truth_kcal.values())
bc = Counter(bucket(k) for k in truth_kcal.values())
bk = defaultdict(float)
for i, k in truth_kcal.items():
    bk[bucket(k)] += k
for b, (name, _, _) in enumerate(BUCKETS):
    print(f"  {name:16s} lines {bc[b]:3d} ({bc[b]/len(rows):5.1%})   share of all recipe kcal {bk[b]/tot:5.1%}")
queue = [i for i, r in rows.items() if r["fixed"]["status"] != "matched"]
qb = Counter(bucket(truth_kcal[i]) for i in queue)
print(f"  of the {len(queue)} lines the (fixed) matcher sends to review: "
      + ", ".join(f"{BUCKETS[b][0]}: {qb[b]}" for b in range(4)))

# ================================================================ B. model predicts materiality
print("\n=== B. Model-predicted calorie bucket from line text only (no USDA data) vs reference ===")
truth_b = {i: bucket(k) for i, k in truth_kcal.items()}
for m, res in out1f.items():
    pred, exact, near, tp, fp, fn, tn = {}, 0, 0, 0, 0, 0, 0
    for i in rows:
        s = res[str(i)].get("cal_score")
        if s is None:
            continue
        pred[i] = s
        pb = min(3, int(round(s)))
        exact += pb == truth_b[i]
        near += abs(pb - truth_b[i]) <= 1
        material_truth = truth_b[i] >= 2
        flag = s >= 1.5
        tp += flag and material_truth; fp += flag and not material_truth
        fn += (not flag) and material_truth; tn += (not flag) and not material_truth
    n = len(pred)
    miss_kcal = sum(truth_kcal[i] for i in pred if pred[i] < 1.5)
    print(f"  {m:42s} exact bucket {exact/n:5.1%} | within 1 bucket {near/n:5.1%} | "
          f"flag material(>=50kcal) recall {tp/(tp+fn):5.1%} precision {tp/(tp+fp):5.1%} | "
          f"kcal in lines NOT flagged: {miss_kcal/tot:4.1%} of total")

# ================================================================ C. impact-aware triage on gold sample
print("\n=== C. Impact-aware triage on the gold sample (weighted to 531 lines; truth = gold-best food kcal) ===")
GW = {i: W[v["stratum"]] for i, v in gold.items()}
truth_g = {i: (line_kcal(i, v["best"]) if v["kind"] == "food" else 0.0) for i, v in gold.items()}
evalable = [i for i, v in gold.items() if v["kind"] in ("food", "not_food")]  # kcal truth defined
TOT_G = sum(GW[i] * truth_g[i] for i in evalable)
N_RECIPES = 50


def options_kcal_and_probs(m: str, i: int):  # type: ignore[no-untyped-def]
    o = out1f[m].get(str(i), {})
    probs = o.get("match")
    if not probs:
        return None
    return [(o["options"].get(k), p) for k, p in probs.items()]  # key 'none' -> fdc None


def expected_kcal_error(m: str, i: int) -> tuple[str | None, float, float] | None:
    dist = options_kcal_and_probs(m, i)
    if dist is None:
        return None
    top_fdc, top_p = max(dist, key=lambda t: t[1])
    k_top = line_kcal(i, top_fdc)
    e = sum(p * abs(line_kcal(i, f) - k_top) for f, p in dist)
    return top_fdc, top_p, e


def realised(i: int, fdc: str | None) -> float:
    return abs(line_kcal(i, fdc) - truth_g[i])


def summarise(name: str, decide) -> None:  # type: ignore[no-untyped-def]
    auto = err = 0.0
    for i in evalable:
        d = decide(i)
        if d is not NotImplemented:
            auto += GW[i]
            err += GW[i] * realised(i, d)
    review = sum(GW.values()) - auto  # weights over ALL gold lines
    print(f"  {name:52s} review {review:4.0f} lines ({review/N_RECIPES:4.1f}/recipe)   residual kcal error {err/TOT_G:5.2%} of recipe kcal")


# NotImplemented = send to review (human assumed correct -> 0 error)
def baseline(i):  # type: ignore[no-untyped-def]
    f = rows[i]["fixed"]
    return f["decidedFdcId"] if f["status"] == "matched" else NotImplemented


summarise("deterministic fixed (auto only when `matched`)", baseline)
summarise("accept fixed top-1 for every line, no review", lambda i: (rows[i]["fixed"]["candidates"] or [{"fdcId": None}])[0]["fdcId"])
for m in out1f:
    short = m.split("/")[-1]

    # A top answer of `none` is never an automatic resolution: it goes to review (a person, or a
    # separate is-it-food gate, decides whether to drop the line). Only real food picks auto-resolve.
    def conf_policy(i, t, m=m):  # type: ignore[no-untyped-def]
        r = expected_kcal_error(m, i)
        return r[0] if r and r[0] is not None and r[1] >= t else NotImplemented

    def impact_policy(i, eps, m=m):  # type: ignore[no-untyped-def]
        r = expected_kcal_error(m, i)
        return r[0] if r and r[0] is not None and r[2] <= eps else NotImplemented

    for t in (0.8, 0.9):
        summarise(f"{short}: confidence >= {t}", lambda i, t=t: conf_policy(i, t))
    for eps in (2, 5, 10, 25):
        summarise(f"{short}: expected kcal error <= {eps} kcal", lambda i, e=eps: impact_policy(i, e))

    # Materiality gate: lines the model predicts as calorie-negligible are never put in front of a
    # person (top pick used as-is, `none` = dropped); everything else uses the expected-kcal rule.
    def gated_policy(i, eps, gate, m=m):  # type: ignore[no-untyped-def]
        s = out1f[m][str(i)].get("cal_score")
        r = expected_kcal_error(m, i)
        if s is not None and s < gate:
            return r[0] if r else None
        return impact_policy(i, eps)

    for eps, gate in ((5, 0.5), (5, 1.0), (10, 1.0)):
        summarise(f"{short}: skip if predicted <{gate} bucket, else <={eps} kcal", lambda i, e=eps, g=gate: gated_policy(i, e, g))

# ================================================================ D. end-to-end vs published
print("\n=== D. End-to-end per-recipe calories vs PUBLISHED values (50 recipes, all 531 lines; independent of my labels) ===")
serv = {c["caseId"]: int(re.search(r"\d+", c["yieldText"]).group()) for c in derived["cases"]}
pub = {c["id"]: float(c["reference"]["caloriesKcal"]) for c in manifest["cases"]}
by_case = defaultdict(list)
for i, r in rows.items():
    by_case[r["caseId"]].append(i)


def evaluate(name: str, choose) -> None:  # type: ignore[no-untyped-def]
    errs = []
    for case, idxs in by_case.items():
        kcal = sum(line_kcal(i, choose(i)) for i in idxs) / serv[case]
        errs.append(abs(kcal - pub[case]) / pub[case] * 100)
    within = sum(e <= 20 for e in errs) / len(errs)
    print(f"  {name:58s} median err {statistics.median(errs):5.1f}%  mean {statistics.mean(errs):5.1f}%  within 20%: {within:4.0%}")


evaluate("corpus-pinned foods (reproduces repo benchmark)", lambda i: rows[i]["pinnedFdcId"])
evaluate("as-is matcher, auto-matched lines only (rest counted 0)", lambda i: rows[i]["asis"]["decidedFdcId"])
evaluate("fixed matcher, auto-matched lines only (rest counted 0)", lambda i: rows[i]["fixed"]["decidedFdcId"])
evaluate("fixed matcher top-1 for every line (accept defaults)", lambda i: (rows[i]["fixed"]["candidates"] or [{"fdcId": None}])[0]["fdcId"])
for m, res in out1f.items():
    short = m.split("/")[-1]

    def top(i, m=m, res=res):  # type: ignore[no-untyped-def]
        o = res[str(i)]
        p = o.get("match")
        if not p:
            return None
        k = max(p, key=p.get)
        return None if k == "none" else o["options"].get(k)

    def hybrid(i, m=m, res=res):  # type: ignore[no-untyped-def]
        o = res[str(i)]
        p = o.get("match")
        if p:
            k = max(p, key=p.get)
            if p[k] >= 0.8:
                return None if k == "none" else o["options"].get(k)
        c = rows[i]["fixed"]["candidates"]
        return c[0]["fdcId"] if c else None

    evaluate(f"{short}: top-1 for every line", top)
    evaluate(f"{short}: top-1 if conf>=0.8 else fixed matcher top-1", hybrid)

# ================================================================ E. nutritionally-equivalent ties
print("\n=== E. Deterministic rule: exact-score ties whose kcal barely differs (no model needed) ===")
ties = [i for i, r in rows.items() if r["fixed"]["status"] == "ambiguous" and is_tie(r["fixed"])]
print(f"  fixed-matcher exact ties: {len(ties)} lines")
for eps in (2, 5, 10):
    ok = 0
    for i in ties:
        c = rows[i]["fixed"]["candidates"]
        top = [x for x in c if abs(x["score"] - c[0]["score"]) < 1e-9]
        ks = [line_kcal(i, x["fdcId"]) for x in top]
        ok += (max(ks) - min(ks)) <= eps
    print(f"  tie kcal spread <= {eps:2d} kcal on the line: {ok:3d} of {len(ties)} ({ok/len(ties):5.1%}) could auto-resolve with no model")
