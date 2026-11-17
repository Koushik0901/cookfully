# Decision-model use cases: backlog

Status: **brainstorm, nothing here is built** except what is marked *shipped*. Written 2026-11-17.

Context: matching assist (`docs/decision-model-assist.md`) is the only shipped use. The research and
offline experiments are in [`decision-model-experiments/`](decision-model-experiments/README.md). This
file is the wider backlog of places the same models (Jev, Clef and others via the OpenRouter Decisions
API) could help, including features the app does not have yet.

## What the models are good for

A decision model reads a short state (text, JSON, optionally an image) and typed questions, then returns
probabilities in one parallel pass: `choice` (which option), `noul` (does this hold), `score` (where on a
scale), `box` (where in an image; Jev 1.14 only). The sibling Extractions API returns typed fields,
including `estimate` with p10/p90. They cannot write text or explain, and they are weak at exact numbers.

Cost: the offline experiments averaged about **$0.00003 per call** (6,670 calls, $0.18, short prompts).
That is a measurement from our own runs, not a price list; re-check before budgeting.

## Principles for getting the most out of cheap calls

1. **Verify everything, not just the ambiguous cases.** Run two or three models and send disagreements
   to a person.
2. **Enrich data ahead of time.** Label a corpus once (offline) instead of asking at runtime.
3. **Ask many small, atomic questions per item** in one parallel request.
4. **Compute at write time and cache by input hash.**
5. **Use the probability as UX** (confidence chips, review ordering), not just as a threshold.
6. **Tune every threshold per model on our own labeled data.** Probabilities differ between models.
7. **Keep nutrition math, safety rules and side effects in code.** The model supplies judgment only.
8. **Degrade to the deterministic result** on any failure, and fail closed for safety checks.

## Evidence tiers

- **Tested**: measured in our own experiments (PR #12).
- **Pattern**: a documented vendor or practitioner pattern, not yet tried on food.
- **Speculative**: depends on untested capabilities (vision, camera).

## The 23 use cases

### A. Nutrition integrity

| # | Use case | Primitive | Evidence |
|---|---|---|---|
| 1 | **Second opinion on every match.** Run 2-3 models over every auto-matched line, not only ambiguous ones; disagreement goes to review. The matcher's auto-matches were still ~12% wrong vs gold (cooked rice matched to rice crackers). | `choice` | Tested (matching), ensemble untested |
| 2 | **Pre-label the whole USDA table once.** For ~8,000 foods ask: raw or cooked, branded or generic, plant or animal, allergen flags. One-time cost around a dollar; gives the matcher features at zero runtime cost. | `choice` + `noul` | Pattern |
| 3 | **Raw vs cooked and prep state.** "1 cup cooked rice" and "1 cup chopped onion" need different grams; pick the state per line. | `choice` | Pattern |
| 4 | **Grams for count items.** "1 medium onion" as a p10/p90 range feeding the existing range-based nutrition. | Extractions `estimate` | Pattern, untested |
| 5 | **Nutrition-label photo to owner food.** Photograph a label and fill in the owner-created food. | Extractions + image | Speculative |

### B. Safety and dietary needs

| # | Use case | Primitive | Evidence |
|---|---|---|---|
| 6 | **Hidden-ingredient check.** Per ingredient and per avoid-list item: "does Worcestershire contain anchovy?" About 30 calls per recipe. Adds warnings on top of the deterministic ingredient lists; **never the only allergen check**; fail closed. | `noul` | Pattern |
| 7 | **Diet tags with confidence.** Cuisine and meal type, plus vegan / gluten-free / dairy-free. Show "probably vegetarian" with the probability; flag conflicts with the ingredient list. | `choice` + `noul` | Pattern |

### C. Imports

| # | Use case | Primitive | Evidence |
|---|---|---|---|
| 8 | **Prompt-injection guard.** "Does this text try to instruct an AI?" on imported web text before it reaches Needle2 or OpenRouter. | `noul` | Pattern |
| 9 | **Verify cleanup output.** Enforce "cleanup cannot invent ingredients": "did the cleaned output add an ingredient not in the source?" | `noul` | Pattern |
| 10 | **Cleanup triage.** "Is this parse already clean?" Escalate only messy imports to the costlier LLM. | `noul` | Pattern |
| 11 | **Ingredient-line gate.** Drop headings, notes, nutrition labels and parser fragments. In PR #12: 61 of 62 junk lines at P(junk) >= 0.8 with 0 of 58 real ingredients dropped (not yet compared against Needle2). | `noul` | Tested |
| 12 | **Recipe page sorting.** Real recipe vs blog filler vs note vs step vs headnote. | `choice` | Pattern |
| 13 | **Photo and receipt import.** Handwritten recipe cards, cookbook pages, receipts and fridge photos to pantry items. Needs the multimodal models (Clef Omni). | Extractions + image | Speculative |

### D. Planning and shopping

| # | Use case | Primitive | Evidence |
|---|---|---|---|
| 14 | **Soft-preference scoring for suggestions.** The solver finds nutritionally feasible candidates; models score variety, "feels like a real dinner" and ingredient overlap. 200 candidates x 4 questions is under two cents. | `score` | Pattern |
| 15 | **Recipe attributes for planner and search.** Effort, active time, "weeknight-friendly", "keeps 4 days", "freezes well", "reheats well", "needs an oven". | `score` + `noul` | Pattern |
| 16 | **Substitutions.** "Is milk plus vinegar OK for buttermilk in this recipe?" with a threshold; pair with deterministic ratio tables. | `noul` | Pattern |
| 17 | **Grocery cleanup.** Merge "scallions" and "green onions", classify store aisles, decide "a staple you probably have". | `choice` + `noul` | Pattern |
| 18 | **Shelf-life gaps.** Put unknown pantry items into lifespan buckets (fills `expiry_lifespans`). | `choice` | Pattern |
| 19 | **Taste learning.** A few liked and disliked recipes in the state, then "would they like this?". Keep requests short; long ones degrade. | `noul` | Pattern |

### E. Cooking

| # | Use case | Primitive | Evidence |
|---|---|---|---|
| 20 | **Voice-command router.** Pick the intent (next, repeat, scale, substitute, how long) with a confidence; re-ask below the threshold. A fast first stage ahead of Needle2's function calls. | `choice` | Pattern |
| 21 | **Timer and step detection.** Find "simmer 20 minutes" and passive vs active steps; could build a real cooking timeline. | `noul` + `score` | Built (`step_timers`) |
| 22 | **Thumbnails.** Use `box` to find the dish and set the focal point automatically; score PDF thumbnail candidates so food beats logos and ads. | `box`, `score` | Speculative |

### F. Meta

| # | Use case | Primitive | Evidence |
|---|---|---|---|
| 23 | **Model-assisted labeling.** The research gold labels were made by an LLM. A second model pre-screens so a human only reviews disagreements. | `choice` | Pattern |

## Suggested order

| Priority | Idea | Why |
|---|---|---|
| 1 | #1 Verify all matches with two models | Builds on tested matching and an existing gold set |
| 2 | #2 Pre-label USDA foods | Cheap, one-time, helps every match |
| 3 | #6 Hidden-ingredient check | Highest safety value |
| 4 | #8 and #9 Import guard and cleanup verifier | Closes a real gap for the remote deployment |
| 5 | #7 and #15 Tags and recipe attributes | Unlocks search and planning |
| 6 | #14 and #16 Soft-preference scoring, substitutions | New user-facing value |

Measure each gain with the offline harness in `scripts/decision-model-eval/` before shipping anything.
The design and pull-request plan is in
[`decision-model-implementation-plan.md`](decision-model-implementation-plan.md).

## Cautions

- Every use sends text (or images) to a third party. Anything built must be controlled from Settings,
  use the encrypted OpenRouter key, and degrade to the deterministic result.
- The Decisions and Extractions endpoints are **alpha** and may change.
- Models give no explanation, so the UI can show confidence but not a reason.
- Option order can sway answers; shuffle or test for it.
- Treat all input as data, not instructions: injection applies to decision models too.
- Safety features (#6, #7) supplement the deterministic checks and never replace them.
