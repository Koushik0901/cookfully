"""Experiment 1h: review-effort estimate (UX proxy) and a worked example recipe.

Effort model (ASSUMPTIONS, stated in the report): a review item costs 1 tap when the suggestion shown
first is acceptable, else 4 actions (open picker, search, scroll, choose). Time: 3 s per confirm tap,
15 s per manual pick. Skipped/auto lines cost nothing. Weighted gold sample -> 531 lines, 50 recipes.
Usage: python exp1h_ux.py <workdir> <usda-dir> <repo-root>
"""

from __future__ import annotations

import contextlib
import io
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path(str(HERE / "exp1f_impact.py"), run_name="impact")
gold, rows, out1f, GW, W = g["gold"], g["rows"], g["out1f"], g["GW"], g["W"]
expected_kcal_error, line_kcal, evalable, truth_g = g["expected_kcal_error"], g["line_kcal"], g["evalable"], g["truth_g"]
M = "typesafe/jev-1.14"
N_RECIPES = 50


def correct(i, fdc):  # type: ignore[no-untyped-def]
    return fdc is not None and gold[i]["kind"] == "food" and fdc in set(gold[i]["acceptable"])


def jev_pick(i):  # type: ignore[no-untyped-def]
    r = expected_kcal_error(M, i)
    return (r[0] if r else None), r


def policy_det(i):  # type: ignore[no-untyped-def]
    f = rows[i]["fixed"]
    top = (f["candidates"] or [{"fdcId": None}])[0]["fdcId"]
    return ("auto", None) if f["status"] == "matched" else ("review", top)


def policy_gated(i):  # type: ignore[no-untyped-def]
    s = out1f[M][str(i)].get("cal_score")
    pick, r = jev_pick(i)
    if s is not None and s < 1.0:
        return ("skip", pick)
    if r and pick is not None and r[2] <= 5:
        return ("auto", pick)
    return ("review", pick)


def policy_conf(i):  # type: ignore[no-untyped-def]
    pick, r = jev_pick(i)
    return ("auto", pick) if (r and pick is not None and r[1] >= 0.9) else ("review", pick)


def summarise(name, policy):  # type: ignore[no-untyped-def]
    n_rev = confirm = manual = 0.0
    for i in gold:
        kind, suggestion = policy(i)
        if kind != "review":
            continue
        w = GW[i]
        n_rev += w
        if correct(i, suggestion):
            confirm += w
        else:
            manual += w
    actions = confirm * 1 + manual * 4
    seconds = confirm * 3 + manual * 15
    print(f"  {name:44s} review items/recipe {n_rev/N_RECIPES:4.1f} | one-tap confirms {confirm/N_RECIPES:4.1f} | manual picks {manual/N_RECIPES:4.1f} | "
          f"~{actions/N_RECIPES:4.1f} actions, ~{seconds/N_RECIPES:3.0f} s per recipe")


print("=== Review effort per imported recipe (weighted estimate; assumptions in file header) ===")
summarise("deterministic matcher (fixed), review the tail", policy_det)
summarise("Jev, auto at confidence >= 0.9, review the rest", policy_conf)
summarise("Jev, skip negligible + expected-kcal rule (<=5 kcal)", policy_gated)

# worked example: a real corpus recipe with several gold-labelled lines
by_case: dict[str, list[int]] = {}
for i, v in gold.items():
    by_case.setdefault(rows[i]["caseId"], []).append(i)
case = max(by_case, key=lambda c: len(by_case[c]))
print(f"\n=== Worked example: {case} ({len(by_case[case])} gold-labelled lines) ===")
print(f"  {'line':46s} {'kcal':>5s}  deterministic         Jev gated policy")
for i in sorted(by_case[case]):
    kcal = line_kcal(i, gold[i]["best"]) if gold[i]["kind"] == "food" else 0
    d = policy_det(i)[0]
    k = policy_gated(i)[0]
    print(f"  {rows[i]['originalText'][:44]:46s} {kcal:5.0f}  {d:12s}  ->  {k}")
