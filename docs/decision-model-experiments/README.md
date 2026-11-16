# Decision models (Jev, Clef and others) for Cookfully: research and experiments

Date: 2026-11-15 · Branch: `decision-ai-use-cases-1dd803` · Nothing in the application was changed.
Experiment code: [`scripts/decision-model-eval/`](../../scripts/decision-model-eval) · Raw outputs and frozen labels: [`results/`](results)

## 1. Summary

1. **Fix the deterministic matcher first.** In a harness that runs the real `FoodMatcher` over the full USDA
   pool (8,156 foods), any food that is not in the ~45-word lexicon in `food_semantics.py` is hard-rejected
   (`celery` vs `Celery, raw` is an `identity_conflict`), because `_identity()` falls back to the *last token*
   and USDA names put the identity first. This alone explains 151 of 153 `unmatched` corpus lines. Ignoring the
   conflict when either identity is a guess raises "acceptable food in the top-8 candidates" from **61% to 92%**.
   It is free and needs no model. **Now fixed in this branch** (uncommitted): `identity_conflict` only rejects
   when both identities come from the curated lexicon/aliases (`food_semantics.py`), with regression tests.
   Re-running the harness against the unpatched code path now gives 205 auto-matched / 77 unmatched / 12
   zero-candidate lines (before: 143 / 153 / 151). A related scoring gap remains: category-first USDA names such
   as "Nuts, walnuts, english" score 0.73 for "walnuts", below the 0.80 auto-match bar.
2. **Decision models are a strong fit for the part that is left**: choosing among candidates, deciding when a
   person must look, and recognising non-ingredient lines. On 140 blind-labelled lines, when the right food was
   among the options the models picked it **94–99%** of the time (deterministic top-1: 73%).
3. **The best way to use their probabilities is your butter-vs-lime idea, done per nutrient.** Auto-resolve a
   line when the model's *expected error in every tracked nutrient* is under ~2% of the daily value. Jev with
   that rule: **4.5 review items per recipe (today: 6.8) and ≤0.6% residual error in kcal, protein, fat, carbs,
   sodium and vitamin C** (today: 5–10%). A calorie-only "skip negligible lines" rule looks even better
   (2.9 items) but **leaves 8% sodium and 36% vitamin C error**, so do not use calories alone.
4. **Import cleanup is promising, duplicate detection is inconclusive.** Jev flagged 61 of 62 junk lines at
   P(junk) ≥ 0.8 (all 62 at ≥ 0.5) with 0 of 58 real ingredients dropped, including 13 of 14 real parser
   fragments; the importer's deterministic detectors caught 5 of 62 and 0 of those 14. Cheap ingredient overlap
   already solves the synthetic duplicate test, so it does not show a model advantage.
5. **Cost is negligible** (all experiments: 6,670 calls, **$0.18**). The real costs are a new outbound data
   path for a self-hosted app and an alpha API. See §6.

## 2. What decision models are, and how people use them (research)

**Capabilities.** A decision model reads a `state` (text, JSON, optionally images/audio/video) and typed
questions, and returns a probability-bearing answer per question, in one parallel pass and with no generated
text or explanation ([OpenRouter Decisions API](https://openrouter.ai/docs/guides/features/decisions.md)):

| Primitive | Asks | Returns |
|---|---|---|
| `choice` | which one of these options | winning key, probability per option, confidence |
| `noul` | does this condition hold | probability of yes |
| `score` | where on this ordered scale | probability per level and a probability-weighted position |
| `box` (Jev 1.14 only) | where in this image | bounding box |

A sibling **Extractions API** returns typed fields (`text`, `number`, `date`, `list`, `estimate` with
p10/p90, `forecast`) with spans and a "nothing here" probability, and can read photos
([guide](https://openrouter.ai/docs/guides/community/extractions.md)). OpenRouter lists 41 decision models
(Jev, Clef/Clef Flash/Clef Omni, OpenAI, Microsoft, Perplexity, Liquid, Upstage, Kev 4B and others); input
input prices run from free to about $0.19 per million tokens, and outputs are free ([Jev hub](https://openrouter.ai/docs/guides/community/jev.md)).

**What people build with them** (all vendor docs or vendor-adjacent write-ups unless noted):

- **Classification and tagging at scale**: one `choice` for exclusive categories plus one `noul` per tag; pick a
  threshold per tag from a small labelled sample; log cost per 1,000 items
  ([cookbook](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-classification.md); 550 tweets for $0.014).
- **Routing and triage**: support tickets, intent, review urgency, model/effort routing (the "Jev Router").
- **Guardrails and agent oversight**: gate risky tool calls or shell commands, auto-approve routine permission
  prompts, leave ambiguous ones to a human ([cookbook](https://openrouter.ai/docs/cookbook/building-agents/gate-tool-calls-with-jev.md)).
- **Cost cascades**: draft with a cheap model, verify against retrieved context with a decision model, escalate
  only on failure ([cookbook](https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade.md)).
- **LLM-as-judge**: Scale Labs reports System-1 judges reaching 90–93% on JudgeBench with a written reference
  answer, at about 1/16 the cost of a reasoning judge, and that the spread *between* decision models is larger
  than the gap to frontier judges, so model choice matters ([Scale Labs](https://labs.scale.com/blog/to-jev-or-not-to-jev)).
- **Extraction and coding of free text**: e.g. police crash narratives into probabilistic variables
  ([arXiv 2609.24052](https://arxiv.org/abs/2609.24052); I read only the abstract page).
- **Multimodal gating**: image/audio/video in the same `state` ([Clef](https://developers.cloudflare.com/changelog/post/2026-10-01-clef-workers-ai/)).

**How practitioners extract the strengths** ([TypeSafe build guide](https://docs.typesafe.ai/concepts/how-to-build-with-system-one),
[confidence guide](https://docs.typesafe.ai/confidence)):

1. Keep deterministic rules, side effects and control flow in code; use the model only for the judgment.
2. Decompose: short, atomic questions; send only the state each question needs.
3. Branch on probabilities, and **set thresholds per action by the cost of being wrong**, tuned on your own
   labelled data ("test thresholds by plotting confidence against accuracy").
4. Combine several independent answers in code; ask many questions in one request (they run in parallel).
5. Route low-confidence cases to a person or a stronger model, and **fail closed** on refusals or missing answers.
6. Treat the input as data, never as instructions.

**Limits** ([jaggedness page](https://docs.typesafe.ai/model-jaggedness/jev-1.13), Scale Labs): weak at numeric
precision and multi-hop indirection; no explanations; calibration is a group property, not a per-answer
guarantee; option order can sway answers; probabilities differ per model, so **thresholds must be re-tuned
for each model** (I saw this: Clef is far less peaked than Jev); long requests degrade. The Decisions and
Extractions endpoints are **alpha**. Benchmark claims are mostly vendor-run. I found **no published use of
decision models for food, nutrition or entity matching**, so §3–§5 are new evidence, not a replication.

## 3. How the experiments were run

- **Inputs:** the repo's 50-recipe nutrition corpus (531 ingredient lines, with grams, published per-serving
  nutrition and pinned USDA foods) and the pinned Foundation 2026-04-30 and SR Legacy 2018-04 datasets
  (checksums verified), 8,156 foods.
- **Baseline:** the real `FoodMatcher` and compatibility code, with a stub repository that mimics the SQL
  shortlist (top 256) and the default hashing embedder. **This is not the live app** (no database, no
  fastembed, no remembered choices).
- **Gold labels:** I labelled 140 stratified lines **blind** (shuffled options, no scores, no pinned marker;
  several acceptable options allowed; explicit "none"/"not a food") and froze them before any model call
  (SHA-256 `e6be02ad…be22f24`, [`gold_labels.json`](results/gold_labels.json)). **The labeller is an LLM**, not a
  human; the corpus's pinned ids are algorithmically derived, so I did not use them as truth. Please
  spot-check ~20 lines. Results are weighted back to all 531 lines.
- **Models:** Jev 1.14, Clef, Clef Flash, Liquid d1, Kev 4B, Perplexity Decider Flash v1.3 (free) and OpenAI GPT-6
  Luna Decisions. Candidate options = what the app could show (top-8 fixed + lenient + as-is, max 14, no pinned
  injection). The model sees the original line, the parsed name and the recipe title, never USDA nutrients.
- **Not tested:** Needle2 (the app's existing model layer), Clef Omni and image input, the Extractions API,
  repeat-run stability, option-order bias, users, recipes outside the corpus.

## 4. Results: matching ingredients to the nutrition database

**Candidate generation is the first bottleneck** (food lines, weighted):

| | as-is | with identity fix (harness only) |
|---|---|---|
| acceptable food is the top candidate | 49.6% | 68.1% |
| acceptable food within top-8 | 61.5% | 91.6% |
| lines with zero candidates | 151 | 12 |
| auto-matched lines (`matched`) | 143 | 205 |
| of those, wrong vs gold | ~13% | ~12% |

Examples of deterministic auto-matches that were wrong: `cooked rice` → rice crackers, `parmesan` →
fat-free parmesan topping, `oil spray` → industrial coconut oil, `chicken broth` → canned chicken, no broth.
Provenance of the claim: the fallback was introduced in `c90e66f` (2026-08-17); the unit tests contain no
non-lexicon foods. Whether it regressed after the "v2 verified" note in `AGENTS.md` needs a bisect.

**Models pick well when the right food is shown** (raw sample, 106 food lines where an acceptable option was shown):

| model | picked an acceptable food | | model | picked an acceptable food |
|---|---|---|---|---|
| Clef | 99.1% | | Liquid d1 | 97.2% |
| Perplexity Flash v1.3 | 98.1% | | Luna | 96.2% |
| Jev 1.14 | 97.2% | | Kev 4B | 94.3% |
| Clef Flash | 97.2% | | **deterministic top-1** | **72.6%** |

Overall top-1 (counting "right food not shown" as a miss) is 87–92%, capped at 92.4% by candidate recall.

**Confidence thresholds** (share of 531 lines resolved without review, and wrong among them):
deterministic 36% resolved / 12% wrong; Jev at 0.8: 52% / 0 wrong of 74 sampled lines (95% upper bound
about 4%); Luna at 0.8: 56% / 0; Perplexity: 51% / 1%; Clef needs ~0.7 (flatter probabilities); **Clef Flash at
0.8: 42% / 6% wrong, not recommended**; Kev 4B resolves only 25%.

**Impact-aware triage** (kcal and per-nutrient truth = gold-best food × the corpus grams; review lines are
assumed resolved correctly by a person; Jev 1.14; weighted):

| policy | review items / recipe | residual error: kcal · protein · fat · carbs · sodium · vitamin C |
|---|---|---|
| deterministic (fixed), review the rest | 6.8 | 6.7% · 7.1% · 4.8% · 9.6% · 9.0% · 0.1% |
| Jev confidence ≥ 0.9 | 5.9 | 0.5% · 0.2% · 0.7% · 1.1% · 2.6% · 12.1% |
| Jev expected kcal error ≤ 5 kcal | 4.2 | 0.2% · 1.5% · 0.3% · 0.2% · 0.6% · 0.1% |
| **Jev expected error ≤ 2% DV in every nutrient** | **4.5** | **0.3% · 0.3% · 0.4% · 0.2% · 0.6% · 0.1%** |
| Jev kcal rule + skip "negligible kcal" lines | 2.9 | 0.5% · 1.7% · 0.4% · 0.7% · **8.2%** · **35.9%** |

"Expected error" = Σ p(option) × |nutrient(option) − nutrient(top option)| × grams/100, using the model's own
probabilities and USDA values the app already stores. It is the reason a tie between two olive oils costs
nothing to auto-resolve while an uncertain butter does not.

Why the calorie-only skip fails: calories are concentrated (see below), but sodium and vitamin C are not.

**Where the calories live** (531 lines, kcal of the line as written): 205 lines (39%) are under 10 kcal and hold
0.5% of recipe calories; the 117 lines over 200 kcal (22%) hold 81%. Of the 326 lines the fixed matcher sends to
review, 139 are under 10 kcal. Jev predicts a line's calorie bucket from text alone with 75% exact, 93% within
one bucket, which is useful for *ordering* a review list but not safe as the only skip rule.

**End to end against the corpus's published per-serving calories** (50 recipes, independent of my labels):
corpus-pinned foods 17.9% median error (reproduces the repo benchmark); **Jev top-1 on every line 19.6%**
(Luna 19.9%, Clef 21.4%, Perplexity 23.3%); the shipped matcher's top-1 on every line 42.3%. Caveats: the
pinned matches come from the corpus build script's curated queries, not from `FoodMatcher`; the "auto-matched
only" figures (73%/68% median error) are **coverage gaps** (unmatched lines count as 0 kcal), not accuracy; and
the per-line grams come from the pinned foods' densities, which slightly favours the pinned foods.

**A deterministic win that needs no model:** of 197 exact-score ties, 26% (≤2 kcal on the line) to 36% (≤10
kcal) are nutritionally equivalent and could auto-resolve.

## 5. Results: import cleanup and duplicates

**Cleanup** (58 real ingredient lines; 14 real parser fragments such as `0.25 g`, `divided`, `chopped`; 48
synthetic junk lines: headings, notes, nutrition labels, steps, equipment, meta; labelled by construction):

| detector | real fragments caught (of 14) | synthetic junk caught (of 48) | real ingredients wrongly dropped (of 58) |
|---|---|---|---|
| importer's deterministic detectors | 0 | 5 | 0 |
| Jev, P(junk) ≥ 0.8 | 13 | 48 | 0 |
| Jev, P(junk) ≥ 0.9 | 12 | 47 | 0 |
| Clef / d1 / Luna / Perplexity, ≥ 0.8 | 11–12 | 47–48 | 0 |

The app already runs Needle2 with a validated OpenRouter fallback for cleanup; **I did not compare against
it**, so this shows the headroom over the deterministic detectors only. About 16% of corpus lines (estimated
from the labelled sample) are non-food or have no catalog entry, which is why this also protects matching.

**Duplicates: inconclusive.** Synthetic positives (retitled, shuffled, a line or two dropped) and 24 hard
negatives from the same site: ingredient-token Jaccard and every model score AUROC 1.0, with 0 false merges;
today's exact-title merge key finds 0 of the retitled duplicates. A model adds nothing measurable until tested
on genuinely hard semantic duplicates.

## 6. What I would do, in order

1. **Fix `_identity()` / the hard identity filter** (separate change, with a regression test on non-lexicon foods
   such as celery, blueberries, walnuts) and add the **nutritionally-equivalent tie** rule. Both are
   deterministic, free and testable. Re-measure afterwards; the model's marginal gain shrinks but stays.
2. **Add an optional "decision assist" for matching.** Re-rank the top ~12 candidates, then apply the per-nutrient
   expected-error rule to choose auto-resolve vs review. Store the probabilities, model id/version and the
   rule's tolerance next to the existing provenance, mark the result `estimated`, never override manual or
   owner foods, and re-tune thresholds per model. Prefer Jev, Luna or Perplexity Flash for precision; Clef needs
   its own threshold; do not use Clef Flash or Kev 4B for auto-resolution.
3. **Use the same output for the review screen:** order items by nutrition at stake, show a one-tap "looks
   right" for the model's pick, and group low-impact lines under "assumed (n items, ≈x kcal, y mg sodium)".
   Estimated effort at stated assumptions (1 tap to confirm, 4 actions to pick manually; 3 s per confirm, 15 s
   per manual pick): about 19 actions / 70 s per recipe today, about 14 actions / 49 s with confidence-only
   Jev, and about 5 actions / 17 s for the calorie-gated variant (which I do not recommend). The recommended
   nutrient-aware rule sits between the last two; I did not compute its effort. **These are estimates, not
   measured behaviour.**
4. **Cleanup:** benchmark a decision-model `is-ingredient` gate against Needle2 on real PDF imports before
   changing the importer.
5. **Later, untested here:** the Extractions API (`estimate` fields with p10/p90 for "1 medium onion" grams;
   receipt, recipe-card or pantry photos), and self-hosted Clef weights.

**Privacy and deployment.** This is a new outbound data path for a self-hosted app whose OpenRouter fallback
defaults to off. Keep the same pattern: optional, off by default, owner toggle under Settings → Intelligence,
deterministic fallback when unavailable. What leaves the machine: the ingredient line, parsed name, recipe
title and candidate USDA descriptions; no account data. The alpha API can change. A self-hosted route
(open-weight Clef or Kev 4B) removes the data path, but Kev 4B was the weakest model here.

## 7. Reproduce

```bash
# baseline (needs the project venv): three conditions over all 531 lines
uv run --directory backend --frozen python ../scripts/decision-model-eval/exp1_baseline.py --usda-dir <dir> --out <work>
python scripts/decision-model-eval/make_adjudication_sheet.py <work>     # blind sheet; labels were then frozen
COOKFULLY_ENV_FILE=<.env> python scripts/decision-model-eval/exp1_models.py <work>   # models x gold lines
python scripts/decision-model-eval/exp1_eval_models.py <work>            # thresholds, calibration, non-food
python scripts/decision-model-eval/exp1_uncertainty.py <work>            # conditional accuracy, bootstrap
COOKFULLY_ENV_FILE=<.env> python scripts/decision-model-eval/exp1f_models.py <work>  # all 531 lines
python scripts/decision-model-eval/exp1f_impact.py <work> <usda-dir> .   # impact-aware triage, end to end
python scripts/decision-model-eval/exp1i_nutrients.py <work> <usda-dir> .  # per-nutrient residuals
uv run --directory backend --frozen --all-extras python ../scripts/decision-model-eval/exp2_build.py <work>
COOKFULLY_ENV_FILE=<.env> python scripts/decision-model-eval/exp23_models_eval.py <work> .
```

Sources: [OpenRouter Decisions guide](https://openrouter.ai/docs/guides/features/decisions.md) ·
[Jev hub](https://openrouter.ai/docs/guides/community/jev.md) ·
[Extractions](https://openrouter.ai/docs/guides/community/extractions.md) ·
[TypeSafe: build](https://docs.typesafe.ai/concepts/how-to-build-with-system-one), [confidence](https://docs.typesafe.ai/confidence), [jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) ·
[Scale Labs](https://labs.scale.com/blog/to-jev-or-not-to-jev) ·
[Cloudflare Clef changelog](https://developers.cloudflare.com/changelog/post/2026-10-01-clef-workers-ai/) ·
[InfoQ on Clef](https://www.infoq.com/news/2026/10/clef-decision-models/) ·
[Red Hat decision-model guardrail benchmark](https://developers.redhat.com/articles/2026/10/02/benchmarking-ai-decision-models-against-traditional-guardrails) (listed; I did not extract its results).
