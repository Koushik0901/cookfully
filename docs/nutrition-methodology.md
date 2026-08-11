# Nutrition methodology

Vigor & Vine treats nutrition as an evidence-backed planning estimate. It is not medical advice. Every displayed result carries a serving basis, calculation state, coverage, provenance, assumptions, and active corrections so a user can judge and revise it.

## Resolution pipeline and precedence

For the current recipe input hash, the application resolves source-provided nutrition when suitable or derives nutrition from matched ingredients and reference foods. Ingredient corrections are applied before reference matching and gram conversion. Nutrient and yield corrections are applied after the full-recipe rollup, and the result is then divided by the corrected positive serving yield. Active manual corrections therefore take precedence over calculated values in recipe displays and, as later phases consume the same resolved nutrition, in plan totals, suggestions, exports, HTTP responses, and MCP reads.

Original ingredient text is immutable evidence alongside structured parsing. Ingredient matches, household-measure conversions, density/count assumptions, reference release identifiers, input hashes, and calculation timestamps remain inspectable. Recalculation does not overwrite an active correction unless the user explicitly resets it.

## Coverage and completeness

Only non-optional ingredients participate in required coverage. The pipeline computes:

- quantified-mass coverage: matched, convertible grams divided by all quantified, convertible non-optional grams;
- ingredient-count coverage: resolved non-optional ingredient count divided by all non-optional ingredient count.

The published `coverageRatio` is the lower of those two values. A missing or zero denominator produces zero rather than an optimistic result. A benchmark recipe is nutrition-complete only when calories, protein, carbohydrate, and fat are all non-null and coverage is at least `0.900000`.

## Precision and rounding

Ingredient quantities and per-serving nutrients are stored to six decimal places; serving quantities are stored to three. Public JSON values are canonical decimal strings, never binary floating-point numbers. Intermediate and final quantization uses round-half-up.

Recipe screens retain the canonical strings. Plan-entry display snapshots, when introduced in P3, multiply resolved per-serving values by the serving count and round calories to 1 kcal and macros to 0.1 g. Meal, day, and week totals sum those already display-quantized values so the visible entries always add exactly to the visible total.

## Accuracy corpus

The reproducible corpus version `2026-08-10.1` contains 50 captured public recipe pages: 15 simple, 20 moderate, and 15 complex recipes across four source sites, multiple cuisines and dietary patterns, metric and imperial measures, ambiguous foods, and conversion risks. A fixed 30-recipe primary subset (9 simple, 12 moderate, 9 complex) is the constitutional release gate; the other 20 cases extend and stress it. No case or unexplained outlier may be dropped to improve a result.

An eligible comparison reference must publish an unambiguous yield and per-serving calories, protein, carbohydrate, and fat. Published page values are comparison targets only: they cannot be copied into, or used to satisfy, the ingredient-derived accuracy result. Estimates are independently derived from captured ingredient text and versioned USDA FoodData Central Foundation Foods (`2026-04-30`) and SR Legacy (`2018-04`) extracts. Reviewed benchmark decisions may identify a food, gram weight, conversion, or explicit exclusion, but never inject the page's target macros.

The gate runs with:

```powershell
uv run --directory backend vigor-vine nutrition-corpus run --require-pass
```

It writes the full, primary, source-site, complexity, and per-case report to `backend/tests/fixtures/nutrition-corpus/reports/nutrition-accuracy.json`.

## Error calculation and gates

For each eligible nutrient observation at or above its near-zero floor, percentage error is:

`abs(estimate - reference) / reference * 100`

The release metric is the median across every eligible recipe after per-serving yield normalization. The maximum permitted median error is 20% for calories and 25% each for protein, carbohydrate, and fat.

Near-zero references are excluded only from that nutrient's percentage summary because percentage error becomes unstable near zero. They remain in the corpus and are reported separately using median and maximum absolute error. The floors are 50 kcal, 5 g protein, 5 g carbohydrate, and 2 g fat.

The checked-in report currently records:

| Scope | Import complete | Nutrition complete | Calories median | Protein median | Carbohydrate median | Fat median |
|---|---:|---:|---:|---:|---:|---:|
| Full 50 | 50/50 (100%) | 49/50 (98%) | 17.923171% | 9.351875% | 23.229545% | 20.422063% |
| Primary 30 | 30/30 (100%) | 29/30 (96.6667%) | 17.351242% | 7.057937% | 23.185922% | 19.771130% |

All three product criteria pass in both scopes: at least 90% nutrition completeness (SC-001), independently ingredient-derived median error within every threshold (SC-002), and at least 90% complete import of title, yield, ingredients, and instructions (SC-003). The full report also records 9 near-zero protein, 7 carbohydrate, and 6 fat cases; every calorie reference is at least 50 kcal.

## Food matching: scoring, signals, and ambiguity

Ingredient names from recipes are matched against active USDA reference foods (Foundation Foods 2026-04-30 and SR Legacy 2018-04) through a deterministic, non-AI pipeline:

1. **Candidate retrieval.** The database returns up to 30 foods whose singular/plural token variants all appear (containment ordering via `&&` overlap). Token singularisation normalises *bananas* → *banana* and *leaves* → *leave* so canonical rows are never excluded by raw-token mismatch.

2. **Full-containment gate.** Auto-match is only eligible when *every* query token appears in the candidate — partial coverage never auto-matches, preserving the `unmatched` result contract.

3. **Ranking signals** (additive, no multiplicative cap):
   - **Lead token** (+0.12): candidate starts with a query token (*Chicken, …* for "chicken breast").
   - **Contiguous block** (+0.08): all query tokens appear in one adjacent window, any order, reflecting USDA noun-phrase inversion (*Yogurt, Greek, …* for "greek yogurt").
   - **Head-phrase identity** (+0.05): the query's English head noun matches the candidate's USDA identity segment (pre-comma phrase): *Rice* for "Rice, brown, …" vs. *Flour* for "Rice flour, brown".

4. **Penalty lexicons** (−0.05 each) for unmatched tokens that signal a different product form (*flour, powder, dehydrated, canned, breaded, tenders, roll, soufflé, salad, dry* …), flavour variant (*strawberry, vanilla, mesquite, cinnamon* …), or plant part (*leave, peel, seed, stalk, stem*). Mild unmatched-descriptor penalty (−0.01) for remaining unmatched tokens.

5. **Ambiguity = exact ties only.** When the top candidate has a strictly higher quantised score than the second, confidence is treated as sufficient (≥ 0.80 required, margin > 0). Genuine ties — *plain low-fat* vs. *plain non-fat* yogurt, *extra-light* vs. *extra-virgin* olive oil — stay ambiguous with ranked alternatives for user adjudication via the corrections flow. This avoids the silent-wrong-pick risk observed in conventional fuzzy matchers while keeping the common-case input burden low (12 of 15 staple queries resolve cleanly in the live corpus).

6. **Density bridging.** When the ingredient uses a volume unit (cups, tablespoons) the pipeline consults a look-up table (`volume_assumptions.density_for`) keyed on the matched food's description. The density is passed to `to_grams`; missing density raises `DomainError` rather than guessing.

The algorithm was designed against the Mealie/Tandoor reference architectures (see `docs/inspiration-review.md` § ingredient→food matching), which match against a user's small curated food list where exact + plural lookup suffices. USDA-scale matching required containment gating, corpus-convention-aware head-phrase recognition, and explicit ambiguity — all three of which are absent from those projects.

## Limitations

- Reference labels and recipe sites may use different ingredient brands, edible portions, preparation states, or rounding conventions than USDA entries.
- Household measures, produce sizes, drained weights, and count conversions require assumptions even when reviewed.
- Optional toppings and "to taste" ingredients are excluded unless explicitly included, so actual consumption can differ.
- Published nutrition can itself be inaccurate; the benchmark measures agreement with qualified published references, not laboratory truth.
- Coverage describes resolved ingredient quantity, not biological variability or individual absorption.
- The corpus is deliberately broad but cannot represent every cuisine, supplement, branded food, or site markup pattern. Version changes require a new captured corpus and report rather than silent fixture replacement.
- Users with allergies, metabolic conditions, eating disorders, pregnancy-related needs, or clinical nutrition targets should verify data with qualified professionals and primary labels.

