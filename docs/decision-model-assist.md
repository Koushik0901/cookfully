# Decision-model assist for ingredient matching

On by default; it does nothing until an OpenRouter key is saved in Settings. Implements recommendation 2 of
[`decision-model-experiments`](decision-model-experiments/README.md). Deterministic matching always
runs first; this layer can only *replace* its result when it is safe to.

## How it works

1. `FoodMatcher.decide` produces a decision and its candidate foods (remembered choices, manual
   matches and owner foods are never sent to the model).
2. Up to 12 candidates (plus a reserved `none` option) go to a decision model as one `choice` question.
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

Everything is set in the app under **Settings → Intelligence → OpenRouter**; there are no environment
variables for it.

- **API key.** Write-only. It is encrypted (Fernet, key derived from `COOKFULLY_SECRET_KEY`) before
  it is stored, only its last four characters are kept for display, and no endpoint returns it. If
  the secret key changes the stored key stops decrypting and is treated as unset; enter it again.
- **Smarter ingredient matching** switch (on by default; it only acts once a key is saved).
- **Matching model** (default `typesafe/jev-1.14`). Thresholds are per model; re-tune if you change it.
  The research advises against Clef Flash and Kev 4B for auto-resolution.
- **Auto-resolve tolerance** as a percent of daily value (default 2, allowed up to 10).
- **Import cleanup model**, used only when the import-cleanup OpenRouter fallback is switched on.

Changes apply to the next recipe processed; nothing needs a restart. Per-call limits (8 s timeout,
12 candidates) are fixed in code.

**Privacy.** The ingredient line, parsed food name, recipe title and candidate USDA descriptions go
to OpenRouter. No account data is sent. The Decisions endpoint is alpha and may change.

## Not done yet

- Review-screen ordering by nutrition at stake and the one-tap "looks right" confirmation.
- Re-measuring on the live app; the research numbers came from an offline harness with a stub repository.
- Import-cleanup gate and the Extractions API (research sections 5 and 6).
