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

## Limitations

- Reference labels and recipe sites may use different ingredient brands, edible portions, preparation states, or rounding conventions than USDA entries.
- Household measures, produce sizes, drained weights, and count conversions require assumptions even when reviewed.
- Optional toppings and "to taste" ingredients are excluded unless explicitly included, so actual consumption can differ.
- Published nutrition can itself be inaccurate; the benchmark measures agreement with qualified published references, not laboratory truth.
- Coverage describes resolved ingredient quantity, not biological variability or individual absorption.
- The corpus is deliberately broad but cannot represent every cuisine, supplement, branded food, or site markup pattern. Version changes require a new captured corpus and report rather than silent fixture replacement.
- Users with allergies, metabolic conditions, eating disorders, pregnancy-related needs, or clinical nutrition targets should verify data with qualified professionals and primary labels.

