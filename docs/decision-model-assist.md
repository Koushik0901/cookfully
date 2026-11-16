# Decision-model assist for ingredient matching

On by default; it does nothing until `COOKFULLY_OPENROUTER_API_KEY` is set. Implements recommendation 2 of
[`decision-model-experiments`](decision-model-experiments/README.md). Deterministic matching always
runs first; this layer can only *replace* its result when it is safe to.

## How it works

1. `FoodMatcher.decide` produces a decision and its candidate foods (remembered choices, manual
   matches and owner foods are never sent to the model).
2. Up to `COOKFULLY_DECISION_ASSIST_MAX_OPTIONS` candidates (default 12, plus a reserved `none`
   option) go to a decision model as one `choice` question.
3. `domain/decision_assist.py` computes, per tracked nutrient (kcal, protein, fat, carbohydrate,
   sodium, vitamin C), the model's expected error against its top pick as a share of the daily
   value. The line auto-resolves only if that is at most the tolerance (default 2%) in **every**
   nutrient. Calories alone are not enough: the research found a calories-only rule leaves 8% sodium
   and 36% vitamin C error.
4. On auto-resolve the match is stored with `match_method = "decision_assist"` and the probabilities,
   model id, tolerance and per-nutrient expected error in `candidate_evidence`.
5. Anything else keeps the deterministic result: a `none` winner, unknown quantity, malformed or
   missing probabilities, timeout, HTTP error, disabled key.

## Operating it

| Variable | Default | Notes |
|---|---|---|
| `COOKFULLY_DECISION_ASSIST_ENABLED` | `true` | Also needs `COOKFULLY_OPENROUTER_API_KEY`. |
| `COOKFULLY_DECISION_ASSIST_MODEL` | `typesafe/jev-1.14` | Thresholds are per model; re-tune if you change it. The research advises against Clef Flash and Kev 4B for auto-resolution. |
| `COOKFULLY_DECISION_ASSIST_TOLERANCE_DV` | `0.02` | Share of daily value, 0 < x <= 0.1. |
| `COOKFULLY_DECISION_ASSIST_TIMEOUT_SECONDS` | `8` | Per line; failure keeps the deterministic result. |

**Privacy.** Enabling it sends the ingredient line, parsed food name, recipe title and candidate USDA
descriptions to OpenRouter. No account data is sent. The Decisions endpoint is alpha and may change.

## Not done yet

- Review-screen ordering by nutrition at stake and the one-tap "looks right" confirmation.
- Re-measuring on the live app; the research numbers came from an offline harness with a stub repository.
- Import-cleanup gate and the Extractions API (research sections 5 and 6).
