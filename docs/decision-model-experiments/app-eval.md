# Evaluating decision features with the shipped code

`scripts/decision-model-eval/app_eval.py` runs a decision feature end to end with the application's own
code: the deterministic `FoodMatcher` over the pinned USDA Foundation (2024-04) and SR Legacy (2018-04)
foods, the `Decisions` engine, and the feature's rule. It scores the result against the PR #12 gold labels
(`results/gold_labels.json`, 140 lines in five strata).

```bash
# USDA zips as downloaded by the app's reference-data install
uv run --directory backend python ../scripts/decision-model-eval/app_eval.py \
    --usda-dir <dir> --workdir <dir> [--offline] [--budget 1.00] <evaluator>
```

- Answers are cached in `<workdir>/decision_cache.jsonl` through a file-backed engine store, so a rerun
  makes no calls. `--offline` never calls and reports cache misses instead.
- `--budget` caps the total cost of the cache file (default $1.00).
- The transport sends `Authorization: Bearer $OPENROUTER_API_KEY`.

## Why the PR #12 numbers are not reproduced exactly

The PR #12 response cache was never committed, and those experiments used a harness-only patched matcher
(`fixed` in `exp1_baseline.py`), different candidate sets (up to 14, merged from three conditions) and
stratum weights that extrapolate to all 531 lines. They report residual nutrient error and reviews per
recipe. This runner uses the matcher and candidate list exactly as the app does and reports precision on
the gold sample, so the two sets of numbers answer different questions. Both agree on the direction:
the per-nutrient expected-error rule auto-resolves a large share of uncertain lines with very few errors.

## `match-assist` (2026-11-17, superseded by `match-referee`)

The shipped assist rule, applied to lines the matcher left ambiguous or unmatched (84 of the 140 gold
lines have candidates). "Correct" means gold accepts the chosen food; for lines gold marks as not a food
(or as having no acceptable entry) only "no match" is correct.

Deterministic baseline on the 140 lines: `matched` 50 (43 correct, 7 wrong), `ambiguous` 65,
`unmatched` 25.

| panel | tolerance | resolved of 84 | correct | wrong | precision |
|---|---|---|---|---|---|
| Jev | 1% | 36 | 35 | 1 | 97% |
| Jev | 2% | 40 | 39 | 1 | 98% |
| Jev | 5% | 44 | 43 | 1 | 98% |
| Clef | 1% | 27 | 25 | 2 | 93% |
| Clef | 2% | 36 | 34 | 2 | 94% |
| Clef | 5% | 44 | 42 | 2 | 95% |
| Jev + Clef (averaged) | 1% | 28 | 27 | 1 | 96% |
| Jev + Clef (averaged) | 2% | 35 | 34 | 1 | 97% |
| Jev + Clef (averaged) | 5% | 43 | 42 | 1 | 98% |

Cost: 168 answers, $0.011 in total.

Reading: at the default 2% tolerance Jev alone resolves almost half of the uncertain lines at 98%
precision. Averaging Jev with Clef does not improve precision and resolves fewer lines, because Clef's
flatter distributions raise the expected error. A second model earns its place for *disagreement*
(the referee's downgrade rule), not for averaging. The `match-assist` evaluator was replaced by
`match-referee`; its numbers are kept here for comparison.

## `match-referee` (2026-11-17)

The shipped referee (`domain/match_referee.py`) at the default 2% tolerance. On uncertain lines the
primary model's distribution drives the tolerance rule and the other models can only veto. On confident
matches, a line goes to review when every model agrees on a different food that moves a tracked
nutrient past the tolerance, or agrees that no listed food fits (mean probability at least 0.5).

| panel | uncertain lines resolved | right | wrong | confident wrong caught (of 7) | false alarms (of 43) | wrong left in place |
|---|---|---|---|---|---|---|
| Jev | 40 | 39 | 1 | 4 | 3 | 3 |
| Clef | 36 | 34 | 2 | 3 | 2 | 4 |
| **Jev + Clef (default)** | **38** | **38** | **0** | **4** | **2** | **3** |

Compared with the deterministic matcher alone on these 140 lines: 38 more lines are resolved without a
person, none of them wrong; 4 of the 7 wrong confident matches are caught, at the cost of 2 correct
matches sent to review. Lines left for a person: 58 of 140 (deterministic alone: 90 not matched, plus 7
wrong matches nobody looks at). Cumulative cache cost for both evaluators: $0.017.

### Prep state (#49, 2026-11-17)

The referee also asks, in a separate request, what state the line implies (raw, cooked, canned,
unspecified). A confident (mean at least 0.8), agreed state that contradicts the food's USDA state
(for example a cooked line on a raw-rice entry) sends the line to review with a fitting candidate first,
or holds back an upgrade. Asking it in the same request as the match question shifted the match answers
(35 resolved instead of 38, 3 caught instead of 4), so it is asked separately.

On the 140 gold lines the state check changed no outcome: the numbers above are unchanged with it on.
The corpus lines that name a cooked or prepared form already say so in the text, which the
deterministic matcher's semantic filter catches before the referee runs. The check is there for implied
states ("leftover rice", "2 cups rice, prepared"), which this gold set does not contain, so its benefit
is not yet measured. Extra cost: one request per line per model.

## `hidden-ingredients` (2026-11-17)

`results/hidden_ingredients_gold.json`: 54 hand-labelled (ingredient line, avoid item) pairs for
typical store-bought versions, 30 of which contain the item (Worcestershire sauce / fish, pesto / nuts,
soy sauce / gluten, marshmallows / pork…) and 24 that do not (coconut milk / dairy, rice noodles /
gluten…). Ambiguous pairs were left out. Each pair runs through the shipped `check_hidden` with the most
cautious answer across the panel.

| panel | threshold | flagged | recall | precision |
|---|---|---|---|---|
| Jev | 0.5 | 30 | 100% | 100% |
| Clef | 0.5 | 27 | 87% | 96% |
| **Jev + Clef, worst case (default)** | **0.5** | **31** | **100%** | **97%** |
| Jev + Clef, worst case | 0.3 | 35 | 100% | 86% |
| Jev + Clef, worst case | 0.7 | 30 | 97% | 97% |

Clef alone missed red curry paste / shellfish, kimchi / fish, marshmallows / pork and gochujang /
gluten. Taking the worst case across the panel keeps Jev's recall, which is what a warning needs; the
cost is one extra false alarm. The default threshold stays at 0.5. Cost: 216 answers, under $0.01.

## Import checks (2026-11-17)

**`line-gate`** on the PR #12 line set (`results/exp2_dataset.json`: 58 real ingredient lines; 14 real
parser fragments and 48 synthetic headings, notes, nutrition labels, steps, equipment and meta lines).
A line is moved only when every model's P(real ingredient) is at most 0.2.

| panel | junk moved (of 62) | real ingredients moved (of 58) |
|---|---|---|
| Jev | 61 | 0 |
| Clef | 58 | 1 ("1 batch homemade bagels") |
| **Jev + Clef (default)** | **58** | **0** |

The deterministic parse already treats 5 of the 62 junk lines as junk (`baseline_junk`). Needle2 could not
be run here (no local intelligence service), so there is no direct comparison with it yet.

**`import-screen`** on 12 hand-made pages (`results/import_pages_gold.json`: 4 clean recipes, 3 messy
ones, 3 with instructions to an AI hidden in a step or ingredient, an article and a product page). All
three questions are right on all 12 pages for every panel once the "already clean" threshold is 0.5:
injection 0.98–0.99 on the crafted pages against at most 0.10 elsewhere; "already clean" 0.71–0.89 on
clean pages against at most 0.04 on messy ones (the first threshold, 0.8, missed two clean pages with Jev
+ Clef); page kind right every time.

**`cleanup-verifier`** on 20 cleaned lines (`results/cleanup_verifier_gold.json`: 9 invented foods, 11
rewordings such as scallions / green onions, courgettes / zucchini, mince / ground beef). A cleanup is
rejected only when every model puts P(present in source) at or below 0.2.

| panel | invented caught (of 9) | false alarms (of 11) |
|---|---|---|
| Jev | 9 | 0 |
| Clef | 8 | 0 |
| **Jev + Clef (default)** | **8** | **0** |

The miss is chives for spring onions, which Clef accepts as a synonym. Cumulative cost of all
evaluations so far: $0.061.

## `facets` spot-check (2026-11-17)

All 50 corpus recipes, from title and ingredient lines only (the corpus has no steps), with the Jev +
Clef panel in one request per recipe. There are no gold labels, so this is a read-through.

- **Diet tags look right where checkable:** no vegetarian tag on any recipe naming meat, poultry or
  fish (the deterministic conflict check guarantees that); "honey and walnut stuffed dates" is
  vegetarian but not vegan; the endive "tuna salad wraps" are correctly gluten-free.
- **The read-through led to two fixes.** "Weeknight-friendly" fired on 46 of 50 recipes. It now needs
  under 15 minutes hands-on, or 15–30 minutes with minimal effort, and fires on 18. The gluten word
  list gained wraps, pitas, bagels, buns, naan, crackers, tortillas (except corn), bulgur, farro,
  spelt, seitan, orzo, macaroni and lasagna. "X-free" phrases and gluten-free flours, pastas and
  noodles no longer count as gluten.
- **Coverage:** effort and active time on every recipe, meal type on 47, cuisine on 37 (the rest
  "other" or unsure), storage tags on 25–29, oven on 13. About half of the storage tags are below 0.8
  and are shown as "Probably …".
- **Known weakness:** active time is estimated without the method text here, so it leans short; in the
  app the steps are included.

Cost: 100 answers, about $0.02.

## Shelf-life spot-check (2026-11-17)

35 pantry names, live, Jev + Clef. Nine never reach the models: the lifespan table covers mushrooms,
zucchini and sweet potato, and bacon, smoked salmon, oat milk and others need the label date. Of the 26
that do, the panel agreed on 17, all plausible: fresh dill, fresh mint, raspberries and fresh
mozzarella 3 days; hummus and bok choy 7; feta 14; tahini, dried lentils, canned chickpeas, miso,
sauerkraut, frozen peas, rice, pasta, peanut butter, maple syrup, olives, capers and ground cumin
"months" (180). It gave no date for 9 (kimchi, sourdough, mango, pineapple, tortillas, parmesan, fish
sauce, pesto, jalapeños) because the models disagreed, which leaves the date blank as before. Coarse
buckets (180 days for an opened jar of capers is generous) are why the date is marked "estimated" and
editable.

## Grocery tidy spot-check (2026-11-17)

14 names, live, Jev + Clef. Merges: garbanzo beans to chickpea, coriander leaves to cilantro, scallion to
green onion, and nothing else. Onion and red onion, rice and brown rice, and parmesan and cheddar stayed
separate. Aisles were right for all 14 (produce, pantry, dairy and eggs, spices). Only salt and olive oil
were marked "probably have".

## Food labels in the matcher (#39, #50)

`app_eval.py match-labels` labels the 1,259 candidate foods for the 140 gold lines, then compares the
deterministic matcher without and with the label penalty (cost about $0.44, cached).

| | without labels | with labels |
|---|---|---|
| top candidate correct (any status) | 76/140 | 81/140 |
| confidently matched: correct / wrong | 43 / 7 | 45 / 6 |
| ambiguous: correct / wrong | 12 / 53 | 12 / 52 |
| unmatched: correct / wrong | 11 / 14 | 11 / 14 |

Accuracy improved with no regression in any status, so the penalty stays. A spot-check of the labels
themselves found the state agrees with the description word in 115 of 120 foods (96%); the misses
were mostly "dried" labelled as "cooked".

## Auto-resolve tolerance sweep

`match-referee --offline --tolerance 0.02 0.05 0.08 0.12` replayed from the answer cache (no new spend).
For the Jev+Clef panel on the 140 gold lines:

| tolerance | upgraded | right | wrong | left for a person |
|---|---|---|---|---|
| 2% | 38 | 38 | 0 | 58 |
| 5% | 41 | 41 | 0 | 55 |
| 8% | 44 | 44 | 0 | 51 |
| 12% | 46 | 46 | 0 | 48 |

Each step resolves more lines with no wrong ones. The default moves from 2% to 8% (the Settings field
allows up to 10%); 12% is left out only because it is above that cap. Single models are less safe at
wide tolerances (Clef alone: 6 wrong at 12%), which is why the panel average matters.
