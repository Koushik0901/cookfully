"""Experiment 1i: does the calorie-only triage hide error in other nutrients?

Re-scores the same policies as exp1f/exp1h per nutrient (kcal, protein, fat, carbohydrate, sodium,
vitamin C) and adds a nutrient-aware rule: auto-resolve only if the EXPECTED error in EVERY tracked
nutrient is within a tolerance expressed as a share of the daily value (default 1% DV).
Residual error = sum over auto-resolved lines of |picked - gold-best| as a share of the gold total for
that nutrient (review lines assumed resolved correctly by a person), weighted to 531 lines.
Usage: python exp1i_nutrients.py <workdir> <usda-dir> <repo-root>
"""

from __future__ import annotations

import contextlib
import io
import json
import runpy
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path(str(HERE / "exp1f_impact.py"), run_name="impact")
gold, rows, out1f, GW, GRAMS, USDA = g["gold"], g["rows"], g["out1f"], g["GW"], g["GRAMS"], g["USDA"]
evalable = g["evalable"]
N_RECIPES = 50
NUTR = {  # key: (usda nutrient id, unit, daily value)
    "kcal": ((1008, 2047, 2048), "kcal", 2000.0),
    "protein": ((1003,), "g", 50.0),
    "fat": ((1004,), "g", 78.0),
    "carbs": ((1005,), "g", 275.0),
    "sodium": ((1093,), "mg", 2300.0),
    "vitC": ((1162,), "mg", 90.0),
}
TAB: dict[str, dict[str, float]] = {k: {} for k in NUTR}
for path in (USDA / "usda-foundation/foundation.zip", USDA / "usda-srlegacy/srlegacy.zip"):
    with zipfile.ZipFile(path) as z:
        raw = json.loads(z.read(z.namelist()[0]))
    for food in next(v for v in raw.values() if isinstance(v, list)):
        if not food:
            continue
        nut = {n["nutrient"]["id"]: n.get("amount") for n in food.get("foodNutrients", []) if n.get("nutrient")}
        for k, (ids, _, _) in NUTR.items():
            val = next((nut[i] for i in ids if nut.get(i) is not None), 0.0)
            TAB[k][str(food["fdcId"])] = float(val)


def amount(k: str, i: int, fdc: str | None) -> float:
    return GRAMS[i] * TAB[k].get(fdc, 0.0) / 100.0 if fdc else 0.0


M = "typesafe/jev-1.14"
TRUTH = {k: {i: (amount(k, i, gold[i]["best"]) if gold[i]["kind"] == "food" else 0.0) for i in evalable} for k in NUTR}
TOT = {k: sum(GW[i] * TRUTH[k][i] for i in evalable) for k in NUTR}


def dist(i):  # type: ignore[no-untyped-def]
    p = out1f[M].get(str(i), {}).get("match")
    return None if not p else [(out1f[M][str(i)]["options"].get(key), pr) for key, pr in p.items()]


def top_and_conf(i):  # type: ignore[no-untyped-def]
    d = dist(i)
    return (None, 0.0) if d is None else max(d, key=lambda t: t[1])


def expected_err(i, k):  # type: ignore[no-untyped-def]
    d = dist(i)
    if d is None:
        return 1e9
    top = max(d, key=lambda t: t[1])[0]
    return sum(p * abs(amount(k, i, f) - amount(k, i, top)) for f, p in d)


def pol_det(i):  # type: ignore[no-untyped-def]
    f = rows[i]["fixed"]
    return f["decidedFdcId"] if f["status"] == "matched" else NotImplemented


def pol_conf(i):  # type: ignore[no-untyped-def]
    t, c = top_and_conf(i)
    return t if t is not None and c >= 0.9 else NotImplemented


def pol_kcal(i):  # type: ignore[no-untyped-def]
    t, _ = top_and_conf(i)
    return t if t is not None and expected_err(i, "kcal") <= 5 else NotImplemented


def pol_gated(i):  # type: ignore[no-untyped-def]
    s = out1f[M][str(i)].get("cal_score")
    t, _ = top_and_conf(i)
    if s is not None and s < 1.0:
        return t
    return pol_kcal(i)


def make_nutrient_aware(tol_dv: float, skip_negligible: bool = False):  # type: ignore[no-untyped-def]
    def pol(i):  # type: ignore[no-untyped-def]
        t, _ = top_and_conf(i)
        ok = t is not None and all(expected_err(i, k) <= tol_dv * NUTR[k][2] for k in NUTR)
        if ok:
            return t
        if skip_negligible and t is not None:
            # skip only if EVERY nutrient's worst-case plausible swing is below tolerance
            return t if all(expected_err(i, k) <= tol_dv * NUTR[k][2] for k in NUTR) else NotImplemented
        return NotImplemented
    return pol


def report(name, pol):  # type: ignore[no-untyped-def]
    auto = 0.0
    err = {k: 0.0 for k in NUTR}
    for i in evalable:
        d = pol(i)
        if d is NotImplemented:
            continue
        auto += GW[i]
        for k in NUTR:
            err[k] += GW[i] * abs(amount(k, i, d) - TRUTH[k][i])
    review = sum(GW.values()) - auto
    cells = " ".join(f"{k}:{err[k] / TOT[k]:5.1%}" for k in NUTR)
    print(f"  {name:46s} review {review / N_RECIPES:4.1f}/recipe | residual error  {cells}")


print("=== Residual error per nutrient (share of gold total), Jev 1.14, weighted to 531 lines / 50 recipes ===")
print("  (review count here counts lines with no catalog entry as review; the conservative convention)")
report("deterministic fixed (auto when `matched`)", pol_det)
report("Jev confidence >= 0.9", pol_conf)
report("Jev expected KCAL error <= 5", pol_kcal)
report("Jev kcal rule + skip predicted-negligible-kcal", pol_gated)
for tol in (0.01, 0.02, 0.05):
    report(f"Jev nutrient-aware, every nutrient <= {tol:.0%} DV", make_nutrient_aware(tol))
print("\nDaily values used: kcal 2000, protein 50 g, fat 78 g, carbs 275 g, sodium 2300 mg, vitamin C 90 mg.")
print("Tolerance of 1% DV = 20 kcal, 0.5 g protein, 0.8 g fat, 2.8 g carbs, 23 mg sodium, 0.9 mg vitamin C per line.")
