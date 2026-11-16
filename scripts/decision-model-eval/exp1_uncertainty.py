"""Experiment 1e: uncertainty for the food-matching results.

* accuracy conditional on an acceptable food being among the shown options
  (separates "model picked badly" from "candidate generation never showed the right food")
* stratified bootstrap 95% intervals for coverage / wrong-auto at fixed thresholds
* a 2-model agreement rule (both pick the same food with p >= t)
Pure stdlib. Usage: python exp1_uncertainty.py <workdir>
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

WORK = Path(sys.argv[1])
rows = {r["idx"]: r for r in (json.loads(x) for x in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines())}
gold = {int(k): v for k, v in json.loads((WORK / "gold_labels.json").read_text("utf-8")).items()}
out = json.loads((WORK / "exp1_model_outputs.json").read_text("utf-8"))
random.seed(11)


def is_tie(c):  # type: ignore[no-untyped-def]
    cs = c["candidates"]
    return len(cs) >= 2 and abs(cs[0]["score"] - cs[1]["score"]) < 1e-9


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
by_stratum: dict[str, list[int]] = {}
for i, v in gold.items():
    by_stratum.setdefault(v["stratum"], []).append(i)
W = {s: pop[s] / len(ix) for s, ix in by_stratum.items()}


def correct(i, d):  # type: ignore[no-untyped-def]
    return d is not None and gold[i]["kind"] == "food" and d in set(gold[i]["acceptable"])


def top(m, i):  # type: ignore[no-untyped-def]
    o = out[m].get(str(i), {})
    p = o.get("match")
    if not p:
        return None, 0.0
    k = max(p, key=p.get)
    return (None if k == "none" else o["options"].get(k)), p[k]


def shown_has_acceptable(i):  # type: ignore[no-untyped-def]
    opts = set(next(iter(out.values())).get(str(i), {}).get("options", {}).values())
    return gold[i]["kind"] == "food" and bool(opts & set(gold[i]["acceptable"]))


food = [i for i, v in gold.items() if v["kind"] == "food"]
shown = [i for i in food if shown_has_acceptable(i)]
print(f"gold food lines: {len(food)}; with an acceptable food among shown options: {len(shown)} ({len(shown)/len(food):.1%} raw sample)\n")
print("== accuracy when the right food WAS shown (unweighted, raw sample) ==")
for m in out:
    hit = sum(correct(i, top(m, i)[0]) for i in shown)
    print(f"  {m:42s} {hit}/{len(shown)} = {hit/len(shown):.1%}")
base = sum(correct(i, (rows[i]['fixed']['candidates'] or [{'fdcId': None}])[0]['fdcId']) for i in shown)
print(f"  {'fixed deterministic top-1':42s} {base}/{len(shown)} = {base/len(shown):.1%}")


def resample() -> list[int]:
    s: list[int] = []
    for ix in by_stratum.values():
        s += [random.choice(ix) for _ in ix]
    return s


def stats(sample, decide):  # type: ignore[no-untyped-def]
    auto = wrong = 0.0
    for i in sample:
        w = W[gold[i]["stratum"]]
        d = decide(i)
        if d is not None:
            auto += w
            wrong += w * (not correct(i, d))
    return auto, wrong


def ci(vals):  # type: ignore[no-untyped-def]
    vals = sorted(vals)
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]


def policy_model(m, t):  # type: ignore[no-untyped-def]
    return lambda i: (top(m, i)[0] if top(m, i)[1] >= t else None)


def policy_agree(m1, m2, t):  # type: ignore[no-untyped-def]
    def f(i):  # type: ignore[no-untyped-def]
        d1, p1 = top(m1, i); d2, p2 = top(m2, i)
        return d1 if (d1 is not None and d1 == d2 and min(p1, p2) >= t) else None
    return f


def baseline(i):  # type: ignore[no-untyped-def]
    f = rows[i]["fixed"]
    return f["decidedFdcId"] if f["status"] == "matched" else None


print("\n== stratified bootstrap (1000x): auto-resolved share of 531 lines and wrong-auto rate, 95% CI ==")
cases = {"fixed deterministic": baseline}
for m in ("typesafe/jev-1.14", "openai/gpt-6-luna-decisions", "perplexity/pplx-decider-flash-v1.3:free", "liquid/d1", "cloudflare/clef"):
    for t in (0.8, 0.9):
        cases[f"{m.split('/')[-1]} t={t}"] = policy_model(m, t)
cases["agree(jev,luna) t=0.8"] = policy_agree("typesafe/jev-1.14", "openai/gpt-6-luna-decisions", 0.8)
cases["agree(jev,pplx) t=0.8"] = policy_agree("typesafe/jev-1.14", "perplexity/pplx-decider-flash-v1.3:free", 0.8)
samples = [resample() for _ in range(1000)]
for name, fn in cases.items():
    cov, wr = [], []
    for s in samples:
        a, w = stats(s, fn)
        cov.append(a / sum(pop.values())); wr.append(w / a if a else 0)
    a0, w0 = stats(list(gold), fn)
    print(f"  {name:36s} auto {a0/531:5.1%} [{ci(cov)[0]:.1%}-{ci(cov)[1]:.1%}]  wrong-of-auto {(w0/a0 if a0 else 0):5.1%} [{ci(wr)[0]:.1%}-{ci(wr)[1]:.1%}]")
raw_auto = [i for i in gold if policy_model("typesafe/jev-1.14", 0.8)(i) is not None]
print(f"\nraw sample behind Jev t=0.8: {len(raw_auto)} auto-resolved lines, wrong={sum(not correct(i, policy_model('typesafe/jev-1.14',0.8)(i)) for i in raw_auto)} "
      f"(rule-of-three 95% upper bound on wrong rate ~ {3/len(raw_auto):.1%})")
