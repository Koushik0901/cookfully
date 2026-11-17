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
