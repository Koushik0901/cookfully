# Decision-model match referee for ingredient matching

On by default; it does nothing until an OpenRouter key is saved in Settings. Implements recommendation 2 of
[`decision-model-experiments`](decision-model-experiments/README.md). Deterministic matching always
runs first; the referee (`application/match_referee.py`, rule in `domain/match_referee.py`) gives a
second opinion from a panel of models (Jev 1.14 and Clef by default) on every non-memory match.
Measured results are in [`decision-model-experiments/app-eval.md`](decision-model-experiments/app-eval.md).

## How it works

1. `FoodMatcher.decide` produces a decision and its candidate foods (remembered choices, manual
   matches and owner foods are never sent to the model).
2. Up to 12 candidates (plus a reserved `none` option) go to every model on the panel as one `choice`
   question.
3. **No deterministic match** (ambiguous or unmatched): the primary model's distribution must pass
   the expected-error rule below and every other model must agree on the top pick; then the line is
   stored as `matched` with `match_method = "decision_referee"`.
4. **A deterministic match**: if every model agrees on a *different* food (mean probability at least
   0.5) and switching would move a tracked nutrient by more than the tolerance, or the panel agrees no
   listed food fits, the line goes back to review (`ambiguous`, method `decision_referee`) with the
   panel's pick first. Harmless disagreements are confirmed and recorded.
   A separate request asks what state the line implies (raw, cooked, canned, unspecified); a
   confident, agreed state that contradicts the food's USDA state sends the line to review with a
   fitting candidate first, or holds back an upgrade.
5. `domain/decision_assist.py` computes, per tracked nutrient (kcal, protein, fat, carbohydrate,
   sodium, vitamin C), the model's expected error against its top pick as a share of the daily
   value. The line auto-resolves only if that is at most the tolerance (default 8%) in **every**
   nutrient. Calories alone are not enough: the research found a calories-only rule leaves 8% sodium
   and 36% vitamin C error.
6. Every answered line records `candidate_evidence` of kind `match_referee`: action, reason, models,
   the pick with its probability, the impact at stake and the probabilities per candidate. Rows from
   before the referee carry kind `decision_assist`.
7. Anything else keeps the deterministic result: a `none` winner, unknown quantity, malformed or
   missing probabilities, timeout, HTTP error, disabled key.

## The decision engine

All decision-model calls go through one engine, `Decisions.ask` in `application/decisions.py`
(types in `domain/decisions.py`). Features build `Ask`s (purpose, state, typed `Choice` / `Check` /
`Score` questions) and get back `Answers`, possibly empty. The engine:

- sends each ask to every model on the feature's panel and averages their answers (`choice`,
  `check`, `score`), with `agree` and `check_worst` for stricter rules;
- caches every answer in `decision_answers` by model and request hash, so reprocessing an unchanged
  recipe makes no calls (rows older than a year are removed by the retention sweep);
- records each call's cost there too and stops calling once the month's spend reaches the cap
  (default $2.00);
- shuffles choice options reproducibly per model and request, so position bias is not systematic;
- rejects malformed answers per model and returns empty answers for any failure, missing key or
  disabled feature.

The transport (`infrastructure/decision_client.py`) is the only code that knows the wire format;
`ScriptedDecisionTransport` answers from a function for tests and offline replay.

## Reviewing

The editor's **Review food matches** list (and the recipe page's review summary) puts the lines with
the most nutrition at stake first, using the referee's `impactDv`. Where the panel agreed on a food, the
line shows a "Model pick · 94%" chip with the food's name and a **Use this** button. Tapping it saves
the food exactly like choosing it in the picker, including the match memory. The models give no reasons,
so only the probability is shown.

## Avoid list and hidden ingredients

The owner's avoid list (Goals → Personal food context) produces warnings on recipe detail and badges
on planned meals. Lines that name an avoided item, including group members such as shrimp for
"shellfish", are found deterministically (`domain/avoid_list.py`). For every other (line, item) pair the
`hidden_ingredients` feature asks the panel "could this contain it?" and flags the pair when the most
cautious answer is at least 0.5 (`application/hidden_ingredients.py`). Results are stored in
`recipe_insights` under a fingerprint of the recipe, the list, the models and the prompt version. They
are refreshed after nutrition processing and in the background when the list or OpenRouter settings
change. A recipe without a fresh result shows "not checked", never "safe". Model warnings only add to
the deterministic ones. Measured results are in `decision-model-experiments/app-eval.md`.

## Import checks

Run on every import (`application/import_decisions.py`, wired into `RecipeCleanupService`):

- **Line gate:** a line leaves the ingredient list only when every model agrees it is not an
  ingredient. Import review lists moved lines with a **Put back** button; the original text is kept
  in the change log. Runs even when cleanup is off, and never empties a list.
- **Screen:** one request per page. A page that tries to instruct an AI skips remote (OpenRouter)
  cleanup and says so; a page that already looks clean skips cleanup; a page that is not a recipe is
  flagged.
- **Cleanup verifier:** a cleaned ingredient whose words are not in the source is checked against it.
  If every model agrees the food is not there, that cleanup is rejected and the deterministic parse
  is kept.

## Recipe facets

After processing, the `recipe_facets` feature tags each recipe (diet, cuisine, meal type, effort,
hands-on time, keeps four days, freezes, reheats, needs an oven, and a derived "weeknight-friendly").
Diet tags the ingredient list contradicts are dropped deterministically. Tags appear as chips on
recipe detail ("Probably …" below 0.8), can be combined as filters under **Refine recipes**
(`GET /recipes?facet=…`, matched in SQL against stored tags), and storage tags show as badges on
planned meals.

## Taste in suggestions

After processing (and in the background when favourites change) each recipe gets a stored taste score
from the panel: "a satisfying, complete meal?" and, when there are favourites, "would someone who loves
these recipes enjoy this one?" (`application/taste_scores.py`). The suggestion solver still puts
nutrition first. Once the best nutrition distance is known, it may pick among options within 2% of it,
or 2% of one calorie tolerance, preferring higher taste scores and no more than two recipes per
cuisine. It then minimises the distance again within that band. Scores are read from storage, so
suggestions stay deterministic. With no scores the solver behaves exactly as before.

## Grocery tidy and shelf life

When a grocery list is generated, the `grocery_tidy` feature merges names every model agrees are the
same product (scallions and green onions). Quantities are still only summed when units are compatible.
It also assigns a store aisle and marks likely staples ("Probably have"). Each item shows what it
includes, with **Keep separate**, which is remembered. Aisle and staple can be changed per item, and the
choice is remembered for that food (`grocery_tidy_memories`). When a checked-off item has no known
lifespan and needs no label date, the `shelf_life` feature picks a lifespan bucket. The date is marked
"(estimated)" in the pantry.

## Weights for counted ingredients

"1 medium onion" or "2 large eggs" has no gram weight, so it used to be left out of the nutrition
roll-up. The `gram_estimate` feature asks the panel which weight bucket one such item falls in
(`domain/count_weights.py`). The probabilities give a gram range (about the 10th to 90th percentile),
stored on the match as `count_weight_model` with the range in the assumption text; the roll-up uses
the geometric mean of the range. An owner food serving or manual correction always wins, and a panel
that cannot answer leaves the line unresolved exactly as before.

## Operating it

Everything is set in the app under **Settings → Intelligence → OpenRouter**; there are no environment
variables for it.

- **API key.** Write-only. It is encrypted (Fernet, key derived from `COOKFULLY_SECRET_KEY`) before
  it is stored, only its last four characters are kept for display, and no endpoint returns it. If
  the secret key changes the stored key stops decrypting and is treated as unset; enter it again.
- **Monthly spend cap** (default $2.00) with this month's spend from the decision ledger. When the
  cap is reached every decision feature returns no answer until the next month or a higher cap.
- **Decision features**: one row per feature with an on/off switch and its models (up to three,
  comma separated). Every feature is on by default with Jev 1.14 and Clef; untouched features follow
  the code defaults (`DEFAULT_FEATURES`), edited ones are stored in `openrouter_settings.decision_features`.
  Thresholds are per model; re-tune if you change them. The research advises against Clef Flash and
  Kev 4B for auto-resolution.
- **Auto-resolve tolerance** as a percent of daily value (default 2, allowed up to 10).
- **Import cleanup model**, used only when the import-cleanup OpenRouter fallback is switched on.

Changes apply to the next recipe processed; nothing needs a restart. Per-call limits (8 s timeout,
12 candidates) are fixed in code.

**Privacy.** The ingredient line, parsed food name, recipe title and candidate USDA descriptions go
to OpenRouter. No account data is sent. The Decisions endpoint is alpha and may change.

## Not done yet

- Re-measuring on the live app; the research numbers came from an offline harness with a stub repository.
- Import-cleanup gate and the Extractions API (research sections 5 and 6).

## Food labels

Settings → Intelligence → OpenRouter has a **Food labels** panel that labels every USDA reference
food once (state, generic/processed/branded, origin, flavoured, allergens) as a resumable background
job; it also queues itself after a dataset install. Labels are stored per food under a fingerprint of
the description, models and prompt version, so reruns only ask about new or changed foods. The job
stops with a clear message when the spend cap is reached or the feature is off.

The matcher reads confident labels (probability 0.8 or more) as small score penalties on the top 20
candidates: a raw food for a cooked line (or the reverse), a flavoured or processed variant the line
did not ask for. Foods without labels are unaffected. On the gold set this raised top-candidate
accuracy from 76/140 to 81/140; see `docs/decision-model-experiments/app-eval.md`.

## Design stance: use the models, back them with humans and fallbacks

The models are meant to do the work, not to be second-guessed by default. Where a decision could be
wrong, the remedy is a backstop, not a refusal to ask or to act on the answer: a review step the owner can
undo (moved import lines have "put back"), a deterministic result to fall back to when no model answers,
or an explicit "not checked" state when nothing answered. A single answering model is a usable answer;
thresholds are chosen by measurement (`docs/decision-model-experiments/app-eval.md`), not by caution alone.

## Tuned thresholds

Thresholds are set from hand-labeled gold sets, not by caution alone (see
`docs/decision-model-experiments/app-eval.md`): grocery merge 0.5 (all models must still agree), staples 0.3,
aisles 0.5, shelf-life estimates 0.3 (mean of the panel), diet tags shown at 0.6 and worded as certain
at 0.7, food-label confidence 0.7, auto-resolve tolerance 8%. Re-run the evaluators after changing a
prompt, a panel or a model; probabilities differ between models.

