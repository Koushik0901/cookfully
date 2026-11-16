"""Build a *blind* adjudication sheet for a stratified sample of corpus ingredient lines.

Blind = options are shuffled with a fixed seed and show no matcher score, no status, and
no marker for the corpus's pinned id, so labels cannot be anchored on the system under test.
The option pool is the union of the as-is, fixed and lenient candidate sets plus the pinned
food, so the label set is not tied to any one condition.

Label format (``adjudication_labels.json``), one entry per sampled index:
    {"acceptable": ["A","C"], "best": "A", "none": false, "not_food": false}
* acceptable : every listed option a nutrition-conscious cook would accept as representing the
               ingredient (same food, sensible state/form, typical calories within ~20%).
* none       : the ingredient is a real food but no listed option is acceptable.
* not_food   : the line is not a food ingredient (equipment, quantity fragment, heading, ...).

Writes ``adjudication_sheet.txt`` and ``adjudication_key.json`` to the work dir.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

WORK = Path(sys.argv[1])
SEED = 7
STRATA = {"matched": 40, "tie": 35, "amb_other": 20, "recovered": 20, "unmatched": 25}


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


rows = [json.loads(line) for line in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines()]
rng = random.Random(SEED)
sample: list[dict] = []  # type: ignore[type-arg]
for name, size in STRATA.items():
    pool = [r for r in rows if stratum(r) == name]
    sample.extend(rng.sample(pool, min(size, len(pool))))
sample.sort(key=lambda r: r["idx"])

sheet: list[str] = []
key: dict[str, dict[str, str]] = {}
meta: dict[str, str] = {}
for row in sample:
    options: dict[str, dict] = {}  # type: ignore[type-arg]
    for cand in row["lenientCandidates"] + row["asis"]["candidates"] + row["fixed"]["candidates"]:
        options.setdefault(cand["fdcId"], cand)
    if row["pinnedFdcId"] and row["pinnedFdcId"] not in options and row["pinnedDescription"]:
        options[row["pinnedFdcId"]] = {
            "fdcId": row["pinnedFdcId"],
            "description": row["pinnedDescription"],
            "foodCategory": None,
        }
    ordered = list(options.values())
    rng.shuffle(ordered)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    key[str(row["idx"])] = {letters[i]: o["fdcId"] for i, o in enumerate(ordered)}
    meta[str(row["idx"])] = stratum(row)
    sheet.append(f'#{row["idx"]} line: "{row["originalText"]}" | parsed name: "{row["foodName"]}"')
    for i, o in enumerate(ordered):
        cat = f' [{o["foodCategory"]}]' if o.get("foodCategory") else ""
        sheet.append(f"   {letters[i]}) {o['description']}{cat}")
(WORK / "adjudication_sheet.txt").write_text("\n".join(sheet) + "\n", encoding="utf-8")
(WORK / "adjudication_key.json").write_text(json.dumps({"key": key, "stratum": meta}, indent=1), encoding="utf-8")
sizes = {k: sum(v == k for v in meta.values()) for k in STRATA}
print(f"sampled {len(sample)} lines; sheet lines={len(sheet)}; strata sizes: {sizes}")
