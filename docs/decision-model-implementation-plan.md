# Decision models: design and implementation plan

Status: **plan**, written 2026-11-17. Companion to the backlog in
[`decision-model-use-cases.md`](decision-model-use-cases.md) (the 23 use cases are referred to by number).
Only the matching assist (`docs/decision-model-assist.md`) is built today.

## 1. The problem with building 23 features one at a time

Every use case needs the same plumbing: read the owner's settings and the encrypted key, build a request,
call the alpha endpoint, survive timeouts, validate probabilities, cache by input, track spend, record
provenance, and degrade to the deterministic result. Today that plumbing lives in two places:
`infrastructure/decision_client.py` (one hard-coded `choice` question named `match`) and
`application/decision_assist.py`. Built per feature it would be copied 15 times, each copy with its own
bugs, its own cache (or none), and no shared spend limit.

So the design has two layers:

1. **One deep module, `Decisions`**, which owns all of the plumbing behind a one-method interface.
2. **Thin feature modules**, each made of a pure domain rule plus a small application orchestrator. A
   feature never sees HTTP, keys, caches, retries or spend.

## 2. The deep module: `Decisions`

### Interface

```python
# cookfully/domain/decisions.py  (pure: request/answer types and panel aggregation)

@dataclass(frozen=True, slots=True)
class Choice:          # which option
    instructions: str
    options: Mapping[str, str]          # key -> description; the engine adds nothing

@dataclass(frozen=True, slots=True)
class Check:           # "noul": does this hold
    instructions: str
    yes: str
    no: str

@dataclass(frozen=True, slots=True)
class Score:           # where on an ordered scale
    instructions: str
    levels: Mapping[str, str]           # ordered low -> high

Question = Choice | Check | Score

@dataclass(frozen=True, slots=True)
class Ask:
    purpose: Purpose                    # e.g. Purpose.MATCH_REFEREE; selects settings, panel, cache
    state: Mapping[str, str]            # data only, never instructions
    questions: Mapping[str, Question]

@dataclass(frozen=True, slots=True)
class Answers:
    by_model: Mapping[str, ModelAnswers]   # empty when disabled, over budget or every call failed

    def choice(self, name: str) -> Mapping[str, Decimal] | None: ...   # mean over models that answered
    def check(self, name: str) -> Decimal | None: ...                  # mean P(yes)
    def check_worst(self, name: str) -> Decimal | None: ...            # max P(yes): fail-closed use
    def score(self, name: str) -> Decimal | None: ...                  # expected level in [0, 1]
    def agree(self, name: str) -> bool: ...                            # same top option everywhere
```

```python
# cookfully/application/decisions.py

class Decisions:
    def ask(self, asks: Sequence[Ask]) -> list[Answers]: ...

def build_decisions(session: Session) -> Decisions: ...   # reads Settings; the only constructor callers use
```

That is the whole interface. One method; a list in, a same-length list out. A single question is
`ask([one])[0]`. What a caller must know beyond the types:

- **Answers can be empty.** The feature is off, the key is missing or undecryptable, the monthly cap is
  reached, or every model failed. A feature must treat "no answer" as "no opinion" and keep its
  deterministic result, or, for safety features, as "unchecked" (never as "safe").
- **Answers are cached.** The same purpose + model + state + questions returns the stored answer without
  a network call. Changing an instruction string changes the key, so prompts are versioned for free.
- **It blocks.** Calls run concurrently inside (bounded pool) but `ask` returns when all are done or
  timed out. Use it from Celery jobs, or from an API route only for one small request.

### What sits behind it

| Hidden behaviour | Notes |
|---|---|
| Settings resolution | Per-purpose enable flag and model panel, API key via `SecretBox`. |
| Panel fan-out | Each `Ask` goes to every model on the purpose's panel (1 to 3). |
| Cache | `decision_answers` table, unique on `(model, request_hash)`. Reruns of the pipeline are free and idempotent. |
| Spend ledger and cap | Cost from each response is stored on the cache row. Before calling, the month's spend is summed; over the owner's cap, the engine stops calling and returns empty answers. |
| Option-order control | Choice options are shuffled deterministically per (model, request hash) before sending and mapped back, so order bias is not systematic and results stay reproducible. |
| Validation | Unknown keys dropped, values outside [0, 1] or NaN reject the whole answer for that model. |
| Transport | Timeout, one retry on 429/5xx, no retry on 4xx. Logs carry purpose, model and status only, never state text or the key. |
| Injection framing | State values are sent only as `state`, never interpolated into instructions. |

### The seam

There is one external seam, the transport:

```python
class DecisionTransport(Protocol):
    def post(self, model: str, state: Mapping[str, str],
             questions: Mapping[str, dict[str, object]]) -> RawDecision | None: ...
```

Two adapters, so the seam is real: `OpenRouterTransport` (httpx) and `ScriptedTransport` (tests and eval
replay: returns canned answers keyed by purpose and state). Settings and the cache are **not** seams:
tests construct `Decisions(config, transport, session)` directly and use the existing database fixture,
crossing the same interface callers use.

### Alternatives considered

- **One method per primitive** (`choose`, `check`, `score`), the shape of today's client. Rejected:
  three methods for the same plumbing, and it cannot send several questions in one request, which is
  how the cheap models are meant to be used (backlog principle 3).
- **Typed task objects** (`engine.run(task: DecisionTask[T], items) -> list[T]`, where a task builds
  requests and interprets answers). Deeper for callers, but it pulls each feature's judgement rule into
  a generic framework. Rejected in favour of a convention: each feature module exposes a pure
  `interpret(answers) -> Result` function next to its `build_ask(...)`, tested without the engine.
- **A cache table per feature.** Rejected: one table keyed by request hash covers every feature and
  doubles as the spend ledger.

### Deletion test

Delete `Decisions` and every feature reimplements settings, key handling, caching, spend, validation
and retries. It earns its keep. Delete any single feature module and only that feature disappears,
which is what we want.

## 3. Feature modules

Each feature is a purpose, a pure rule in `domain/`, and an orchestrator in `application/`. Several
backlog items merge because they share a request or a storage shape.

| Module | Backlog | What it does | Where it runs | Stores |
|---|---|---|---|---|
| `MatchReferee` | existing assist, #1, #3 | Judges every non-memory match: upgrade an ambiguous line (today's assist), confirm, or **downgrade** a deterministic auto-match the panel disagrees with to review. Asks the prep-state question in the same request. | Recipe pipeline `_match` | `candidate_evidence` (exists) |
| `FoodLabels` | #2 | Labels every USDA food once: raw/cooked/dry, generic/branded/processed, plant/animal, allergen flags. Matcher reads labels as compatibility signals. | Celery job after reference install, plus a Settings button | `food_labels` |
| `ImportScreen` | #8, #10, #11, #12 | Page-level: injection risk, already clean, page kind. Line-level: real ingredient or junk. | Import, before cleanup | import diagnostics + line flags |
| `CleanupVerifier` | #9 | "Did cleanup add an ingredient not in the source?" per added line; reject the cleanup if so. | Import, after cleanup | import diagnostics |
| `HiddenIngredients` | #6 | Per ingredient and per avoid-list item, worst-case P(contains) over the panel. Unanswered = "unchecked". | Pipeline, after match | `ingredient_flags` |
| `RecipeFacets` | #7, #15 | Diet, cuisine, meal type, effort, active time, keeps/freezes/reheats, needs oven. | Pipeline end (rollup), keyed by recipe input hash | `recipe_facets` |
| `TasteScore` | #14, #19 | Per-recipe soft scores computed ahead of time; the solver uses stored scores so ranking stays deterministic. | Facets job, plus after a like or dislike | `recipe_facets` |
| `Substitutions` | #16 | Candidates from a deterministic table, model checks fit in this recipe. | API route on demand | none (cache) |
| `GroceryTidy` | #17 | Synonym merge, aisle, "probably a staple". | Grocery generation | grocery item fields |
| `ShelfLife` | #18 | Lifespan bucket when `FRESH_LIFESPANS` has no entry. | Pantry add | `expires_on`, `expiry_source="model"` |
| `CookAssist` | #20, #21 | Voice intent router ahead of Needle2; timer and active/passive step detection. | Cook mode | step facets |
| Vision features | #5, #13, #22 | Need image state in `Ask` and the Extractions endpoint. | Later | later |
| `GramEstimate` | #4 | Extractions `estimate` p10/p90 for count units with no portion data. | Later | later |
| Labeling tool | #23 | Eval-harness script, not app code. | `scripts/` | files |

### Rules that every feature module follows

- Owner text is preserved. Model output adds flags and evidence beside the original; it never rewrites
  `original_text`, and a junk line is flagged and moved, not deleted.
- Every model-influenced value records purpose, models, probability and the request hash, so the UI can
  show "suggested by a model, 87%" and the owner can override.
- Safety features combine with deterministic checks by OR, use `check_worst`, and show "unchecked"
  when the engine returns nothing.
- Each feature ships with a gold set and a threshold measured on it (see section 6).

### `MatchReferee` in more detail (first feature)

It replaces `DecisionAssist` and the pipeline's `_assisted` helper with one call:

```python
referee.judge(line: RefereeLine, decision: MatchDecision) -> Judgement
# Judgement.decision: the MatchDecision to store; Judgement.evidence: dict | None
```

Rules, all pure, in `domain/decision_assist.py` (renamed `match_referee.py`):

1. **Ambiguous or unmatched line**: today's rule. Auto-resolve when panel-averaged expected error is
   within tolerance in every tracked nutrient and the panel agrees on the top option.
2. **Deterministic auto-match**: if the panel agrees on a *different* candidate and switching would move
   any tracked nutrient by more than the tolerance, downgrade to `ambiguous` with method
   `decision_referee` and the panel's pick first in the alternatives. Disagreements that do not change
   nutrition are recorded but not sent to review, which keeps the review queue short.
3. **Prep state** (#3): a second `Choice` in the same request (raw, cooked, dry, drained, as listed).
   When it contradicts the matched food's state with high probability, apply rule 2.
4. No answers: keep the deterministic decision.

Cost at a 2-model panel: about 24 calls for a 12-ingredient recipe, well under a tenth of a cent.

## 4. Storage and settings

New tables (one migration per PR that needs them):

- `decision_answers`: id, purpose, model, request_hash, answers JSON, cost_usd Numeric, created_at.
  Unique `(model, request_hash)`. Retention sweep removes rows older than a year.
- `food_labels`: food_reference_id, purpose_version, labels JSON (label -> probability), models.
- `ingredient_flags`, `recipe_facets`: subject id, input_hash, key, probability or value, evidence JSON.
  Stale input hashes are ignored on read and replaced on write, like other pipeline outputs.

Settings (`openrouter_settings`, versioned singleton): add `decision_features` JSON validated by a
Pydantic model, `{purpose: {enabled, models: [..]}}`, plus `decision_monthly_cap_usd` (default 2.00).
Every feature defaults to enabled with a two-model panel of Jev 1.14 and Clef where measured, per the
owner's direction that this is a single-owner app. The existing decision-assist columns migrate into
`decision_features["match_referee"]`.

UI: the OpenRouter card in Settings → Intelligence gains a "Decision features" list (toggle and model
panel per feature), spend this month against the cap, and a "Label foods now" action with progress.
Review screens show the model's pick and probability as a chip and order lines by expected nutrient
impact.

## 5. Delivery plan

One pull request per row. Each keeps CI green, adds tests through the module interface, and updates
`docs/decision-model-assist.md` and the backlog status.

| PR | Scope | Done when |
|---|---|---|
| 1 | **`Decisions` engine**: domain types, transport seam with two adapters, cache and spend table, cap, shuffling. Move today's assist onto it with no behaviour change. Settings JSON + migration of existing columns. | Existing assist tests pass unchanged through the new engine; cache hit and cap tests; contract tests for the settings change. |
| 2 | **`MatchReferee`** (#1, #3) with two-model panel, downgrade rule, review ordering and model chip in the UI. | On the PR #12 gold set: wrong auto-matches caught vs. new false alarms reported; UI checked at desktop and 390x844. |
| 3 | **`FoodLabels`** (#2): labeling job, `food_labels`, matcher compatibility signals, Settings action. | Matcher accuracy on the gold set before and after; job is resumable and idempotent. |
| 4 | **`ImportScreen` + `CleanupVerifier`** (#8 to #12). | Line gate matches PR #12 numbers or better; injection guard tested on a crafted page; a cleanup that invents an ingredient is rejected. |
| 5 | **Avoid list + `HiddenIngredients`** (#6). Needs a new owner preference: a list of things to avoid. | Warnings shown on recipe detail and planner; "unchecked" state when the engine is off. |
| 6 | **`RecipeFacets`** (#7, #15) with search filters and planner badges. | Facets recomputed only on input-hash change; filters work at 390x844. |
| 7 | **`TasteScore` + `Substitutions`** (#14, #16, #19). | Solver output stays deterministic for fixed stored scores. |
| 8 | **`GroceryTidy` + `ShelfLife`** (#17, #18). | Merges are reversible by the owner. |
| Later | `CookAssist` (#20, #21), `GramEstimate` (#4), vision (#5, #13, #22), labeling tool (#23). | Each starts with an experiment in `scripts/decision-model-eval/`. |

Order change from the backlog: the referee (#1) comes before food labels (#2). #1 builds on tested
matching results and an existing gold set, so its gain can be measured in the first feature PR; #2's gain
is a pattern we have not yet measured on food.

## 6. Measuring before shipping

`scripts/decision-model-eval/` keeps its own client and cache for experiments. Add one generic runner
that drives the application's `Decisions` engine through `ScriptedTransport` replaying the experiment
cache, so a feature's `interpret` rule is evaluated on gold data with the exact code that ships. Each
feature PR records in `docs/decision-model-experiments/`: gold set size, threshold chosen per model,
precision and recall at that threshold, and cost.

## 7. Risks

- The Decisions and Extractions endpoints are alpha. The transport adapter is the only code that knows
  the wire format, so a change touches one file.
- A downgrade rule that is too eager floods review. The nutrition-impact gate and agreement requirement
  exist to prevent this; the gold set measures it.
- Spend: the cap is enforced inside the engine, so a runaway job stops calling instead of overspending.
- Model output is never the only safety check (#6, #7).
