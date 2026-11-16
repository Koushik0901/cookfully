"""Experiments 2b and 3: import-line classification and duplicate-recipe detection with decision models.

2b  choice over {ingredient, section_heading, note, nutrition_info, instruction, equipment,
    recipe_meta, fragment}; the app-relevant signal is P(ingredient). Dataset from exp2_build.py.
3   noul "same recipe?" over pairs built from the 50 corpus recipes:
      positives (24)      same recipe, retitled with a template + ingredient names only, shuffled,
                          up to 2 minor lines dropped            (SYNTHETIC, cosmetic variation)
      hard negatives (24) different recipes from the same site sharing the most ingredients
      easy negatives (12) random cross-site pairs
    Baselines: exact normalised title (what merge-on-import keys on today), title-token Jaccard,
    ingredient-name Jaccard.
Pure stdlib. Usage: COOKFULLY_ENV_FILE=<.env> python exp23_models_eval.py <workdir> <repo-root>
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dm_client import DecisionClient, choice_probs, noul_prob  # noqa: E402

WORK, REPO = Path(sys.argv[1]), Path(sys.argv[2])
MODELS = ["typesafe/jev-1.14", "cloudflare/clef", "cloudflare/clef-flash", "liquid/d1", "openai/gpt-6-luna-decisions", "perplexity/pplx-decider-flash-v1.3:free"]
random.seed(5)
client = DecisionClient(WORK)
manifest = json.loads((REPO / "backend/tests/fixtures/nutrition-corpus/manifest.json").read_text("utf-8"))
derived = json.loads((REPO / "backend/tests/fixtures/nutrition-corpus/derived-inputs.json").read_text("utf-8"))
title = {c["id"]: c["expectedImport"]["title"] for c in manifest["cases"]}
site = {c["id"]: c["sourceSite"] for c in manifest["cases"]}
names = {c["caseId"]: [i["parsedFoodName"] for i in c["ingredients"] if i["parsedFoodName"]] for c in derived["cases"]}


def auroc(pos: list[float], neg: list[float]) -> float:
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


# ============================================================ 2b cleanup
KINDS = {
    "ingredient": "A real food ingredient with or without a quantity, such as '2 cups flour' or 'olive oil'.",
    "section_heading": "A heading that groups ingredients, such as 'For the sauce'.",
    "note": "A note, tip, credit, caption or cross-reference rather than an ingredient.",
    "nutrition_info": "Nutrition facts such as calories, protein, carbs, fat, fibre or sodium.",
    "instruction": "A cooking step or method sentence.",
    "equipment": "Kitchen equipment or utensils.",
    "recipe_meta": "Servings, yield, times or difficulty.",
    "fragment": "A meaningless fragment, bare quantity or unit, or a preparation word on its own (such as chopped, divided, 0.25 g).",
}


def classify(model: str, item: dict) -> dict:  # type: ignore[type-arg]
    r = client.decide(
        model,
        {"context": "One line extracted from the ingredient list of an imported recipe.", "recipe": title.get(item["recipe"], "recipe"), "line": item["text"]},
        {"kind": {"type": "choice", "instructions": "What kind of line is this?", "criteria": KINDS}},
    )
    return choice_probs(r, "kind") or {}


items = json.loads((WORK / "exp2_dataset.json").read_text("utf-8"))
print("=== 2b. Import cleanup: is this line really an ingredient? (126-line mixed real/synthetic set) ===")
real_ing = [x for x in items if x["label"] == "ingredient"]
junk = [x for x in items if x["label"] != "ingredient"]
print(f"  lines: {len(real_ing)} real ingredients, {len(junk)} junk ({sum(x['source']=='real-artifact' for x in junk)} real parser fragments, {sum(x['source']=='synthetic' for x in junk)} synthetic)")
print(f"  importer's deterministic detectors: junk caught {sum(x['baseline_junk'] for x in junk)}/{len(junk)} ({sum(x['baseline_junk'] for x in junk)/len(junk):.0%}), real ingredients falsely flagged 0/{len(real_ing)}")
cleanup_out: dict[str, list[dict]] = {}  # type: ignore[type-arg]
for m in MODELS:
    with ThreadPoolExecutor(8) as pool:
        probs = list(pool.map(lambda it, m=m: classify(m, it), items))
    cleanup_out[m] = probs
    p_ing = {x["id"]: p.get("ingredient", 0.0) for x, p in zip(items, probs)}
    a = auroc([1 - p_ing[x["id"]] for x in junk], [1 - p_ing[x["id"]] for x in real_ing])
    cells = []
    for t in (0.5, 0.8, 0.9):
        caught = sum(p_ing[x["id"]] < 1 - t for x in junk)      # confident it is NOT an ingredient
        false_drop = sum(p_ing[x["id"]] < 1 - t for x in real_ing)
        cells.append(f"P(junk)>={t}: caught {caught}/{len(junk)}, real dropped {false_drop}/{len(real_ing)}")
    exact = sum((max(p, key=p.get) if p else None) == x["label"] for x, p in zip(items, probs)) / len(items)
    print(f"  {m:42s} AUROC {a:.3f} | exact kind {exact:5.1%} | " + " | ".join(cells))
(WORK / "exp2_model_outputs.json").write_text(json.dumps(cleanup_out), encoding="utf-8")

# ============================================================ 3 duplicates
def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def toks(t: str) -> set[str]:
    return set(re.findall(r"[a-z]+", t.lower())) - {"the", "a", "and", "with", "recipe", "easy", "best", "homemade", "quick", "simple"}


def jac(a: set, b: set) -> float:  # type: ignore[type-arg]
    return len(a & b) / len(a | b) if a | b else 0.0


def ing_tokens(case: str) -> set[str]:
    return set(w for n in names[case] for w in re.findall(r"[a-z]+", n.lower()) if len(w) > 2)


def card(case: str, retitle: str | None = None, shuffle: bool = False, drop: int = 0) -> dict:  # type: ignore[type-arg]
    ings = list(dict.fromkeys(n.lower() for n in names[case]))
    if drop:
        ings = ings[: max(3, len(ings) - drop)]
    if shuffle:
        random.shuffle(ings)
    return {"title": retitle or title[case], "ingredients": ings}


TEMPLATES = ["Easy {t}", "{t} Recipe", "The Best {t}", "{t} (Quick & Simple)", "Homemade {t}"]
cases = sorted(title)
pairs: list[dict] = []  # type: ignore[type-arg]
for c in random.sample(cases, 24):
    pairs.append({"a": card(c), "b": card(c, random.choice(TEMPLATES).format(t=title[c]), True, random.choice([0, 1, 2])), "label": 1, "kind": "retitled duplicate", "ca": c, "cb": c})
bysite = defaultdict(list)
for c in cases:
    bysite[site[c]].append(c)
cand = sorted(((jac(ing_tokens(x), ing_tokens(y)), x, y) for s in bysite.values() for x in s for y in s if x < y), reverse=True)
for _, x, y in cand[:24]:
    pairs.append({"a": card(x), "b": card(y), "label": 0, "kind": "hard negative", "ca": x, "cb": y})
for _ in range(12):
    x, y = random.sample(cases, 2)
    if site[x] != site[y]:
        pairs.append({"a": card(x), "b": card(y), "label": 0, "kind": "easy negative", "ca": x, "cb": y})
print(f"\n=== 3. Duplicate recipe detection ({sum(p['label'] for p in pairs)} positives [synthetic retitles], {sum(1-p['label'] for p in pairs)} negatives [{sum(p['kind']=='hard negative' for p in pairs)} hard]) ===")
pos = [p for p in pairs if p["label"]]
neg = [p for p in pairs if not p["label"]]
for name, score in (
    ("exact normalised title (today's merge key)", lambda p: float(norm_title(p["a"]["title"]) == norm_title(p["b"]["title"]))),
    ("title-token Jaccard", lambda p: jac(toks(p["a"]["title"]), toks(p["b"]["title"]))),
    ("ingredient-token Jaccard", lambda p: jac(ing_tokens(p["ca"]) , ing_tokens(p["cb"]))),
):
    best = max(((sum(score(p) >= t for p in pos) / len(pos), sum(score(p) >= t for p in neg) / len(neg), t) for t in [i / 20 for i in range(1, 21)]), key=lambda x: (x[0] - x[1]))
    print(f"  {name:42s} AUROC {auroc([score(p) for p in pos], [score(p) for p in neg]):.3f} | best threshold {best[2]:.2f}: recall {best[0]:.0%}, false-merge {best[1]:.0%}")
Q = {"same_recipe": {"type": "noul", "instructions": "Are recipe_a and recipe_b the same recipe: the same dish made with essentially the same ingredients, possibly retitled or reworded? Answer no if they are different dishes, even if they share many ingredients or come from the same family of dishes.", "criteria": {"true": "Same dish, same core ingredients; titles or wording may differ.", "false": "Different dishes or clearly different ingredient sets."}}}
for m in MODELS:
    with ThreadPoolExecutor(8) as pool:
        ps = list(pool.map(lambda p, m=m: noul_prob(client.decide(m, {"recipe_a": p["a"], "recipe_b": p["b"]}, Q), "same_recipe"), pairs))
    sc = [x if x is not None else 0.5 for x in ps]
    P = [s for s, p in zip(sc, pairs) if p["label"]]
    N = [s for s, p in zip(sc, pairs) if not p["label"]]
    cells = [f"t={t}: recall {sum(s >= t for s in P)}/{len(P)}, false-merge {sum(s >= t for s in N)}/{len(N)}" for t in (0.5, 0.8, 0.95)]
    hard = [s for s, p in zip(sc, pairs) if p["kind"] == "hard negative"]
    print(f"  {m:42s} AUROC {auroc(P, N):.3f} | " + " | ".join(cells) + f" | hard-neg max P(same)={max(hard):.2f}")
print("\n", client.summary())
