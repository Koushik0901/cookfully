"""Experiment 2a: build the import-cleanup line set and run the importer's own deterministic detectors.

Dataset (126 lines, labelled by construction):
  * 60 REAL ingredient lines from the corpus (gold kind == food)            -> label "ingredient"
  * 14 REAL parser-artifact fragments from the corpus (gold kind == not_food) -> label "fragment"
  * 52 SYNTHETIC junk lines typical of messy web/PDF imports (headings, notes, nutrition labels,
    instructions, equipment, recipe meta) hand-written for this test       -> labelled by kind
Baseline = RecipeImporter._pdf_ingredient_metadata_start / _pdf_instruction_start (the deterministic
detectors the importer already ships); a line is "flagged as junk" when either returns True.

Run: uv run --directory backend --frozen --all-extras python ../scripts/decision-model-eval/exp2_build.py <workdir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cookfully.infrastructure.recipe_importer import RecipeImporter

WORK = Path(sys.argv[1])
rows = {r["idx"]: r for r in (json.loads(x) for x in (WORK / "baseline_matches.jsonl").read_text("utf-8").splitlines())}
gold = {int(k): v for k, v in json.loads((WORK / "gold_labels.json").read_text("utf-8")).items()}

SYNTH = {
    "section_heading": ["For the sauce:", "FOR THE DOUGH", "Marinade", "To serve", "Topping:", "Filling", "For the salad dressing", "Optional extras"],
    "note": ["Note: can be made up to 2 days ahead", "Tip: use a sharp knife for cleaner slices", "See notes below", "(see recipe notes)",
             "Image courtesy of the author", "Photo by Jane Smith", "Recipe adapted from a family cookbook", "Leftovers keep in the fridge for 3 days"],
    "nutrition_info": ["Protein 25g", "Per serving: 320 kcal", "Carbs 40 g fat 12 g", "Calories: 450", "Fiber 6g", "Nutrition information per serving", "Sodium 480mg", "Net carbs 9g"],
    "instruction": ["Preheat the oven to 180C/160C fan", "Cook for 10 minutes until golden", "Whisk until smooth and set aside", "Season to taste and serve warm",
                    "Bring a large pot of water to a boil", "Fold the egg whites in gently", "Bake for 25 minutes", "Stir everything together and let rest for 5 minutes"],
    "equipment": ["Equipment: 9-inch springform pan", "You will need a stand mixer", "Special equipment: piping bag", "large non-stick frying pan",
                  "wooden skewers, soaked in water", "kitchen string", "instant read thermometer", "baking parchment"],
    "recipe_meta": ["Serves 4", "Prep time: 15 minutes", "Total time 45 mins", "Makes 12 muffins", "Difficulty: easy", "Yield: 6 servings", "Cuisine: Italian", "Cook time 20 min"],
}
items: list[dict] = []  # type: ignore[type-arg]
food = sorted(i for i, v in gold.items() if v["kind"] == "food")
for i in food[::2][:60]:
    items.append({"id": f"real-{i}", "text": rows[i]["originalText"], "label": "ingredient", "source": "real", "recipe": rows[i]["caseId"]})
for i in sorted(i for i, v in gold.items() if v["kind"] == "not_food"):
    items.append({"id": f"frag-{i}", "text": rows[i]["originalText"], "label": "fragment", "source": "real-artifact", "recipe": rows[i]["caseId"]})
for kind, texts in SYNTH.items():
    for n, t in enumerate(texts):
        items.append({"id": f"syn-{kind}-{n}", "text": t, "label": kind, "source": "synthetic", "recipe": "NR-001"})
for it in items:
    t = it["text"]
    it["baseline_junk"] = bool(RecipeImporter._pdf_ingredient_metadata_start(t) or RecipeImporter._pdf_instruction_start(t))
(WORK / "exp2_dataset.json").write_text(json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
junk = [x for x in items if x["label"] != "ingredient"]
real = [x for x in items if x["label"] == "ingredient"]
print(f"items={len(items)} (ingredients={len(real)}, junk={len(junk)})")
print(f"importer deterministic detectors: flag {sum(x['baseline_junk'] for x in junk)}/{len(junk)} junk lines; false-flag {sum(x['baseline_junk'] for x in real)}/{len(real)} real ingredients")
by: dict[str, list[int]] = {}
for x in junk:
    by.setdefault(x["label"], [0, 0])
    by[x["label"]][1] += 1
    by[x["label"]][0] += x["baseline_junk"]
print("  by kind:", {k: f"{a}/{b}" for k, (a, b) in by.items()})
