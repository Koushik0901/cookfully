# Inspiration Review Log

This log keeps comparisons with established self-hosted applications explicit and falsifiable. An
inspiration project is evidence that a pattern can work in its own context—not proof that the pattern
fits Cookfully. Likewise, a local design is not preferred merely because it is already implemented.

For each material subsystem review:

1. inspect current official source code, API documentation, or maintained project documentation;
2. state the problem and relevant differences in persona, scale, compatibility burden, and threat model;
3. identify benefits, failure modes, and operational costs in both the reference and proposed designs;
4. record whether the pattern is adopted, adapted, or rejected and link the local contract/test evidence;
5. revisit the conclusion when either project materially changes.

## P5 external access and API keys — 2026-08-10

### Sources inspected

- [Mealie repository](https://github.com/mealie-recipes/mealie) and its maintained API-token workflow
- [Tandoor Recipes repository](https://github.com/TandoorRecipes/recipes) and bearer-token API usage
- [Immich authentication documentation](https://api.immich.app/authentication) and
  [API-key creation contract](https://api.immich.app/endpoints/api-keys/createApiKey)
- [Immich v1.136 API-key behavior change](https://github.com/immich-app/immich/discussions/20133)

### Objective comparison

Mealie and Tandoor prove that a self-hosted recipe application benefits from owner-managed,
long-lived credentials that work with small external integrations. Their comparatively broad token
authority reduces configuration friction, but it gives a leaked automation credential more power than
many integrations require. Recommending a separate non-admin account reduces exposure in a multi-user
system, but does not fit Cookfully's deliberately single-owner model and would introduce a second
identity concept only to compensate for coarse tokens.

Immich's fine-grained API-key permissions and once-only secret presentation better match the local
least-privilege and recoverability requirements. Its history also demonstrates a liability: routes with
missing or ambiguous permission declarations can accidentally widen authority or require breaking
changes when corrected. Immich's large permission catalog is appropriate for its much broader asset
domain, but would be needless configuration burden here.

### Local decision

Adapt the strongest parts rather than copy one implementation:

- owner-created, named, revocable, expiring long-lived credentials;
- raw secret shown exactly once and only a hash stored;
- a small allowlist of domain scopes, defaulting to read-only;
- every MCP tool declares and enforces a scope; undeclared tools fail closed;
- mutations additionally require idempotency keys and optimistic versions;
- token use is rate-limited and audited without logging secrets or personal nutrition values.

Evidence is defined by `specs/001-nutrition-recipe-planner/contracts/mcp-tools.md` and tasks
T115–T127. This decision should be reconsidered if the product becomes broadly multi-user, because
resource ownership and delegated administration would then need a richer authorization model.

## P6 pantry matching and reversible grocery deductions — 2026-08-10

### Sources inspected

- [Mealie shopping-list documentation](https://docs.mealie.io/documentation/getting-started/features/)
  and its maintained repository food/unit model
- [Tandoor shopping documentation](https://docs.tandoor.dev/features/shopping/) and its maintained
  repository food/unit merge and rename behavior
- [Immich stable trash restore contract](https://api.immich.app/endpoints/trash/restoreTrash) and
  [trash settings](https://docs.immich.app/administration/system-settings/)

### Objective comparison

Mealie and Tandoor both validate the usefulness of linking recipes or meal plans to editable shopping
lists and of maintaining reusable food/unit identities. Those patterns reduce repeated entry and make
manual reconciliation understandable. Neither maintained feature description establishes a
nutrition-grade pantry ledger with exact remaining quantities, safe dimensional conversion, or
reversible subtraction. Treating their shopping behavior as proof for automatic pantry deductions
would therefore overstate the available evidence. Their flexible user-defined units are valuable for
recipe capture, but unsafe as an automatic conversion basis when density or package size is unknown.

Immich is not a food-domain reference, so its asset model should not be copied into pantry storage.
Its explicit trash/restore lifecycle does provide useful contrary evidence to irreversible convenience
actions: reversible state is operationally valuable, but it also requires clear state boundaries and
can fail when underlying state changes independently.

### Local decision

Adapt the editable identity and explicit restore ideas while keeping stricter arithmetic boundaries:

- normalize names for discovery but retain the user's display text;
- auto-match only exact unambiguous food identities; expose fuzzy matches for review;
- convert only within mass, volume, or count dimensions, never by an assumed density or package size;
- consume pantry quantities only through an explicit grocery deduction command;
- persist both sides of every six-decimal conversion and refuse reversal after intervening edits;
- keep unmatched, proposed, partial, and missing states visible instead of treating them as zero.

The first evidence is in tasks T128–T138 and their pantry/micronutrient unit and API contract tests.
This decision should be revisited if a future barcode/package model supplies trustworthy package
quantities or if the reference projects add a well-tested pantry ledger with stronger guarantees.

## P9 backup, maintenance, and full-owner erasure — 2026-08-10

### Sources inspected

- [Mealie backup and restore documentation](https://docs.mealie.io/documentation/getting-started/usage/backups-and-restoring/)
- [Tandoor backup documentation](https://docs.tandoor.dev/system/backup/) and
  [update guidance](https://docs.tandoor.dev/system/updating/)
- [Immich backup and restore documentation](https://docs.immich.app/administration/backup-and-restore/),
  [maintenance mode](https://docs.immich.app/administration/maintenance-mode/),
  [system integrity checks](https://docs.immich.app/administration/system-integrity/), and
  [user deletion lifecycle](https://docs.immich.app/administration/user-management/)

### Objective comparison

Mealie's integrated backup screen and explicit destructive-restore warning make a complex operation
approachable. Its documented recovery suggestion to edit a failed backup's JSON can rescue partial
data, but weakens reproducibility and is unsuitable for an erasure-sensitive activation gate unless
the edited artifact is revalidated. Tandoor is unusually candid that its application-level backup is
not yet a complete DR solution; separating PostgreSQL and media and telling operators to test restores
are sound, but consistency and replay remain the operator's responsibility.

Immich supplies the strongest operational reference: explicit maintenance mode, pre-restore points,
automatic rollback on restore failure, storage integrity markers, and delayed versus immediate user
deletion. Those mechanisms fit its multi-user, very-large-asset domain. Copying its delayed user
deletion into this single-owner planner would conflict with the clarified offline exact-confirmation
requirement, and filesystem marker checks alone do not prevent an older backup from resurrecting
previously erased data. None of the three maintained documents establishes an independent,
content-free, hash-chained erasure ledger that gates restored backups.

### Local decision

Adapt their clearest operational lessons—maintenance as an explicit state, destructive confirmation,
database-plus-filesystem completeness, restore integrity checks, rollback before irreversible
commit, and routine restore drills. Go further where the local privacy contract requires it:

- active API/worker/outbox processes hold shared database leases; erasure requires an exclusive lease;
- files move to same-volume quarantine before one durable `owner_owned` ledger append;
- pre-ledger failure rolls back, while post-ledger failure remains visibly maintenance-locked and
  resumes idempotently;
- the independently preserved ledger replays later erasures into every older backup before activation.

This is not asserted to be universally better. It adds a database lock, independent storage,
operator ceremony, and recovery states that smaller installations must understand. Reconsider it if
future evidence shows the ledger cannot be operated reliably, but do not weaken zero-resurrection
without changing the product's explicit privacy guarantee.

## P10 reference performance — 2026-08-10

### Sources inspected

- [Mealie maintained repository](https://github.com/mealie-recipes/mealie) and self-hosting feature documentation
- [Tandoor Recipes maintained repository](https://github.com/TandoorRecipes/recipes) and shopping documentation
- [Immich maintained repository](https://github.com/immich-app/immich) and backup/worker-oriented operator documentation

### Objective comparison

The three projects demonstrate that recipe libraries, editable shopping workflows, and asynchronous
media or data processing can operate in self-hosted container deployments. They differ materially in
user model, asset volume, query shape, nutrition arithmetic, and background workload. No maintained
source reviewed here publishes an apples-to-apples 10,000-recipe, 50-plan-entry benchmark on the local
4-vCPU/8-GiB profile. Absence of such a report is not evidence that they are slow, and the local pass is
not evidence that its architecture is generally superior.

### Local decision

Use their deployed shapes as workload prompts, then measure the actual local contract. T144 therefore
profiles HTTP reads/search, optimistic plan writes, persisted job acknowledgement and polling, grocery
reconciliation, and solver execution independently. Keep raw three-run results and maximums, disclose
the measurement boundary, and rerun before raising scale or concurrency. Evidence and limitations are
in `docs/performance.md` and `artifacts/performance-report.json`.

## First-run presentation: landing and sign-in — 2026-08-11

### Sources inspected

- [Immich login page](https://github.com/immich-app/immich/blob/main/web/src/routes/auth/login/%2Bpage.svelte)
  and its `AuthPageLayout.svelte` (`web/src/lib/components/auth-page/auth-page-layout.svelte`)
- [Immich open-redirect advisory GHSA-8244-8vpr-vp9c](https://github.com/immich-app/immich/security/advisories/GHSA-8244-8vpr-vp9c)
- Mealie's and Tandoor's own landing surfaces for comparison breadth only

### Objective comparison

Immich's unauthenticated page is a full-viewport composition: a single giant, low-opacity brand mark
sits behind a centered, bordered authentication card that groups the form, a remember-me control, and
a small help link. It reads instantly as "this is a real product" while carrying only a login form.
Its liabilities are mostly contextual: the decorative backdrop costs little, but the composition
relies on a large SVG/logo asset, and its `continue` redirect parameter was the vector for a stored
open-redirect/XSS advisory — proof that cosmetic flows still need security review. Mealie and Tandoor
provide no materially better first-run reference, and neither justifies copying a busy dashboard or a
rich landing page that leaks product state before authentication.

### Local decision

Adapt the compositional idea and reject the dangerous parameter:

- the local landing hero uses a static macro ring plus budget bars (the macro ring motif from
  DESIGN.md) instead of a logo asset, staying on-palette with only `--macro-*` and neutral/primary
  tokens;
- the sign-in view uses the same ring as a faint, blurred, non-interactive backdrop behind a centered
  auth card, and the card groups heading, promise copy, the existing `LoginForm`, and a single-owner
  footnote;
- there is no redirect parameter anywhere in the flow, so the Immich open-redirect class of bug is
  structurally absent rather than patched;
- both screens are pure presentational HTML with no pre-authentication data fetches and no external
  font/CDN dependency (fonts ship via fontsource in the bundle), so the first-run screens cannot
  signal product state or exfiltrate anything.

Evidence: `frontend/src/app/App.tsx`, `frontend/src/app/providers.tsx`,
`frontend/src/components/MacroPreview.tsx`, and the UI tests `App.test.tsx` and
`SignInView.test.tsx`. Revisit if a signup or multi-user entry flow is ever introduced, because a
post-authentication redirect target would then need explicit URL validation.

## Internal surfaces: recipe detail, planner, and forms — 2026-08-11

### Sources inspected

- Mealie `mealie/db/models/recipe/nutrition.py`: macro values stored as free-form strings
- Mealie issue #2804 on the recipe nutrition card's missing serving-size basis
- Mealie PR #5165 (recipe-scrapers `nutrients()` fallback) for how imported nutrition is populated

### Objective comparison

Mealie's nutrition card renders whatever string was imported (calories, protein, etc.) without an
authoritative serving basis, and its maintainers publicly acknowledge that this makes the displayed
numbers ambiguous to scale (issue #2804). The model stores macros as strings, so there is no
exact-decimal or coverage concept to present. That is fine for a family recipe organizer, but it is a
liability for a gym user who budgets macros to the gram.

### Local decision

Adopt the compact "facts card" placement idea, adapt the presentation, and reject the ambiguous
basis:

- Cookfully renders macros as color-coded chips (Protein blue, Carbs amber, Fats steel, calories
  as its own accent) on `color-mix` tinted pills, with the serving basis (`Basis: 2.500 servings ·
  Coverage: 88%`), provenance, assumptions, and corrections always in view — the exact-decimal
  contract DESIGN.md and the spec require;
- the weekly planner mirrors the same chip language on entry cards and uses 12px budget bars whose
  consumed portion glows in the macro color, so "at a glance" remains tied to the macro identity,
  not to a second color system;
- no surface mixes another macro-to-color mapping, and calorie/energy stays visually separate from
  the three inviolable macros.

Evidence: `frontend/src/styles/globals.css` (`.macro`, `.budget`, `.micronutrient`,
`.result-banner`, `.objective-grid`, `.recipe-form__section`, `.day-tab--active::after`),
`frontend/src/features/recipes/RecipeDetailPage.tsx`, `frontend/src/features/plans/MealPlanEntry.tsx`,
and `frontend/src/features/recipes/RecipeEditorPage.tsx`. Revisit if Mealie ever adds exact-decimal,
coverage-aware nutrition; there is no current reason to copy its label.

## Ingredient→food matching against a reference corpus — 2026-08-11

### Sources inspected

- [Mealie `services/matching.py`](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/services/matching.py)
  (`find_match`: exact alias-map lookup, then rapidfuzz `fuzz.ratio`, food threshold 85) and
  [`parser_services/_base.py`](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/services/parser_services/_base.py)
  (`DataMatcher`: name + `plural_name` + user aliases)
- [Tandoor `cookbook/helper/ingredient_parser.py`](https://github.com/TandoorRecipes/recipes/blob/develop/cookbook/helper/ingredient_parser.py)
  (`get_food`: exact `name`/`plural_name` match in the user's space, else create; user Automation
  rules rewrite strings before lookup)

### Objective comparison

Both projects match parsed ingredient text against the **user's own small, curated food list**
(tens to hundreds of rows they created), where exact + plural + alias lookup plus a light fuzzy
threshold is adequate. Neither ships a large immutable reference corpus, so neither faces our
actual problem: ~8.1k USDA rows with verbose inverted names where lexically similar but
semantically wrong rows are common (`Milk, buttermilk, fluid, whole` for "whole milk";
`Rice flour, brown` for "brown rice"; dehydrated banana powder for "banana"). Mealie's
`process.extractOne` silently returns the single best fuzzy hit with no ambiguity concept —
acceptable for a family organizer, a provenance violation here. Tandoor's create-on-miss is
meaningless against a fixed corpus, and its Automation rules confirm the shared final fallback:
the user adjudicates. What is genuinely transferable: plural/alias as first-class matching data
(both), exact-before-fuzzy ordering (Mealie), and user adjudication as a designed flow rather
than an error (Tandoor automations ≈ local nutrition corrections).

### Local decision

Reject single-best silent matching and create-on-miss; adopt first-class plural/alias variants
and exact-first ordering; keep the local ambiguity-first contract:

- singular/plural token **variants** drive database-side containment ordering so canonical rows
  (`Bananas, raw`) are not excluded from the candidate window by raw-token array mismatch;
- auto-match is gated on **full query-token containment**; ranking uses lead-token, contiguous
  block, and USDA head-phrase (pre-comma segment) signals, minus penalties for unrequested
  product-form tokens (`flour`, `powder`, `dehydrated`, `canned`, `breaded`, …) and unmatched
  descriptor tokens — no compactness reward, which systematically favored prepared/packaged rows;
- near-ties and low-confidence tops resolve to **ambiguous with ranked alternatives**, never a
  silent wrong pick; the nutrition correction flow is the adjudication path, mirroring the role
  Tandoor's automations play.

Evidence: `backend/src/cookfully/application/food_matching.py`,
`backend/src/cookfully/infrastructure/repositories/nutrition.py` (`search_foods`), and the corpus
tests in `backend/tests/unit/test_food_matching_corpus.py` (including honesty tests that forbid
auto-matching buttermilk over whole milk or banana powder over raw banana). Revisit if a curated
staple-food subset or per-owner frequency data ever justifies a popularity prior.

## Stale nutrition and new plan entries — 2026-08-11

### Sources inspected

- [Mealie repository](https://github.com/mealie-recipes/mealie), whose current documented scope covers
  imported or manually created recipes, weekly meal planning, and shopping lists
- [Tandoor Recipes repository](https://github.com/TandoorRecipes/recipes), whose current documented
  scope covers multiple meals per day, recipe scaling, imported recipes, and shopping lists
- [Immich user-management documentation](https://docs.immich.app/administration/user-management/),
  inspected for its explicit lifecycle framing rather than as a nutrition-planning implementation

### Objective comparison

Mealie and Tandoor validate the general pattern of planning from a recipe collection and preserving
user-editable recipe workflows. Their documented product scope is broader than a nutrition-first
budget: neither source establishes a contract that an ingredient or yield edit invalidates a derived
macro snapshot and must be blocked before a new plan entry. Copying their permissive recipe-to-plan
flow would make sense for cooking schedules, but would risk presenting an old macro estimate as a
current target calculation here.

Immich is not a meal-planning reference, but its documented user lifecycle reinforces a useful
general distinction: visible lifecycle state must not be overwritten merely because related metadata
changes. Its multi-user asset model is much more complex than this single-owner app, so its delayed
deletion and administration structures are not adopted.

### Local decision

Adapt the recipe-manager planning flow but reject permissive planning of stale nutrition:

- existing plan entries remain immutable historical snapshots, so past totals stay reproducible;
- a recipe whose ingredients or yield changed is excluded from new-plan selectors until recalculated;
- the application service independently rejects direct API/MCP attempts with
  `recipe_nutrition_stale`, so UI filtering is not the only guard; and
- manual correction provenance does not hide a stale lifecycle warning.

This is not claimed to be universally better: it adds a recalculation step and can slow a casual
cook. It fits Cookfully because nutrition actively shapes the weekly plan and therefore must remain
trustworthy even though cooking and meal preparation are the primary experience. Evidence:
`backend/src/cookfully/application/meal_plans.py`,
`backend/tests/contract/test_meal_plan_api.py`,
`frontend/src/features/plans/WeeklyPlannerPage.tsx`, and
`frontend/src/features/plans/__tests__/planning-ui.test.tsx`.

## Installation-level model settings and workload preview — 2026-08-18

### Source inspected

- [Immich system settings](https://immich.app/docs/administration/system-settings), especially its
  machine-learning capability switch, operation-specific model sections, availability checks, reset
  defaults action, model-change reprocessing requirement, and concurrency guidance.
- [Immich jobs and workers](https://immich.app/docs/administration/jobs-workers), especially its
  separation of API work from background jobs and its ability to split worker responsibilities.

### Objective comparison

Immich makes expensive processing understandable before it runs: an administrator can choose an ML
backend/model per operation, see availability, tune concurrency, and explicitly re-run the affected
job. That is better than hiding all behavior in environment variables. Immich's remote ML server list
and image-specific model controls are not directly transferable: Cookfully's ingredient matching is
nutrition evidence, and an unavailable or changed model must never silently replace a manual correction
or rewrite a recipe estimate.

### Local decision

Adapt Immich's system-settings pattern into an installation-level **Nutrition Intelligence** section:

- deterministic matching remains the safety baseline; enhanced embeddings are an optional backend,
  not a global nutrition off-switch;
- model name, revision, and bounded concurrency are persisted with optimistic versioning;
- a pre-save estimate calls the fixed Hugging Face metadata host and combines model size, active food
  count, CPU, memory, and disk capacity into a conservative safe/warning/blocked result;
- saving requires the estimate hash, while model loading and nutrition work remain background activity;
- changing settings affects future processing and requires explicit recalculation for existing recipes;
- a Redis lease limits concurrent nutrition-match jobs so the requested concurrency is an actual bound,
  while crashed workers release capacity through expiry;
- remote model URLs, arbitrary code execution, and raw host diagnostics are rejected for now.

This fits Cookfully's narrower requirement: give self-hosting administrators Immich-like control and
visibility without making model similarity a source of silent nutrition authority. Evidence:
`backend/src/cookfully/application/nutrition_intelligence.py`,
`backend/src/cookfully/infrastructure/nutrition_concurrency.py`,
`frontend/src/features/settings/NutritionIntelligenceTab.tsx`, and the resource-estimate contract tests.

## Non-standard unit handling — 2026-08-12

### Sources inspected

- [Tandoor `UnitConversion` model](https://github.com/TandoorRecipes/recipes/blob/develop/cookbook/models.py)
  (`base_amount`, `base_unit` → `converted_amount`, `converted_unit`, optional `food` FK)
- [Tandoor `Food` model](https://github.com/TandoorRecipes/recipes/blob/develop/cookbook/models.py)
  (`properties_food_amount`, `properties_food_unit`, `base_unit`)
- [Mealie `Unit` model](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/db/models/recipe/ingredient.py)
  (`IngredientUnitModel` with name, plural, abbreviation) and its brute-force parser

### Objective comparison

Both Tandoor and Mealie treat units as **user-defined strings** — nothing is hardcoded. A "scoop"
or "pinch" is just another unit label in the database. Tandoor goes further with a `UnitConversion`
table that maps arbitrary units to other units (e.g. `1 scoop → 31g`), optionally scoped to a
specific `Food`. When `food` is `null`, the conversion is generic (e.g. `1 cup → 240ml`). This
single model handles both food-specific and universal conversions. Mealie's parser does not convert
units to weights at all — it stores the raw text and relies on the user's recipe display for sense.

Neither application feeds unit conversions into an automated nutrition pipeline because neither has
one. Their conversions power shopping-list aggregation and ingredient display, not macro rollup.

### Local decision

Adopt the **food-scoped conversion** idea from Tandoor's `UnitConversion.food` FK and reject the
generic-only table for now:

- `owner_foods.typical_serving_g` + `typical_serving_unit` already implements the food-scoped
  pattern — one food entry defines both the nutrition panel and the unit-to-gram conversion;
- the pre-match pipeline at recipe save uses that data to compute `quantity × serving_g` when the
  parsed ingredient unit matches the food's `typical_serving_unit`;
- standard volume/mass conversions (cups, tablespoons, ounces, grams) stay in the Pint-based
  `to_grams` function with density bridging — these are not food-specific;
- a generic `UnitConversion` table (Tandoor-style, `food=null`) is deferred: "pinch", "dash",
  "clove", and "bunch" are trivial to add as owner foods with `typical_serving_g` values, and
  the current pattern avoids a separate model until volume demands it.

Evidence: `backend/src/cookfully/domain/units.py` (Pint-based mass/volume conversion),
`backend/src/cookfully/domain/volume_assumptions.py` (density bridging),
`backend/src/cookfully/application/recipes.py` `_pre_match_owner_foods` (food-scoped
serving conversion), and the Protein Oats coverage demonstration (75% → 100% after creating
a whey protein owner food with `typical_serving_g=31, typical_serving_unit="scoop"`).

## Food-first weekly planning and recipe discovery — 2026-08-12

### Problem being solved

The existing Plan page led with a calorie-budget card and repeated form controls. That made a weekly
meal-prep tool resemble a daily intake tracker. Suggestions also lived in the permanent navigation,
separating inspiration from the two places where it is useful: choosing a recipe and filling a week.
The recipe library exposed database nutrition states more prominently than cooking-oriented ways to
find and organize food.

### Sources inspected

- [Mealie feature documentation](https://docs.mealie.io/documentation/getting-started/features/):
  categories, tags, saved-search cookbooks, calendar planning, notes, random-recipe actions, and
  planner rules that constrain the candidate pool
- [Mealie repository](https://github.com/mealie-recipes/mealie): recipe-first product scope that
  connects a weekly planner and shopping list to the saved recipe collection
- [Tandoor documentation](https://docs.tandoor.dev/) and
  [Tandoor repository](https://github.com/TandoorRecipes/recipes): multiple meals per day,
  meal-plan-to-shopping-list flow, cookbooks, tags, and customizable full-text search
- [ReciMe meal-plan guide](https://recime.app/help/en/articles/14999930-how-to-use-your-meal-plan):
  adding from either a planner slot or recipe detail, moving recipes across a weekly calendar, and
  generating the grocery list from the plan
- [ReciMe overview](https://recime.app/help/en/articles/11594896-que-es-recime) and
  [cookbook guide](https://recime.app/help/en/articles/13571088-how-do-i-create-a-cookbook-on-recime):
  custom cookbooks organized by meal type, cuisine, occasion, or user-defined theme
- [Mob product description](https://careers.mob.co.uk/): personalized recipe feeds, make-ahead and
  weeknight framing, cooking mode, and shopping lists; plus Mob's public recipe discovery surfaces,
  which foreground use cases such as weeknight dinner, family meals, and plan-and-batch

### Benefits and liabilities observed

Mealie and Tandoor offer strong collection management and power-user filtering. Their tag/category
models are flexible, but copying every control into the default Cookfully view would add metadata
work and administration before it improves dinner. ReciMe's direct planner-to-grocery flow and
multiple entry points reduce navigation friction, but its nutrition role is less central than
Cookfully requires. Mob makes inspiration emotionally immediate and frames recipes around real-life
cooking situations, but a publisher-curated feed does not directly map to a private, self-hosted
recipe collection.

### Local decision

Adapt the shared strengths without copying their interfaces:

- remove Suggestions from permanent navigation, while retaining the capability through prominent
  “Give me ideas” and “Help fill this week” actions in Recipes and Plan;
- let every open meal slot launch ideas with its date and meal already selected, and carry the visible
  week into the week-filling flow so inspiration behaves like a layer of planning rather than a
  destination the user must configure again;
- lead suggestion results with the actual dishes, servings, and placement, while keeping nutrition
  totals and deterministic ranking available as evidence behind disclosures;
- make the selected day's meals, servings, and open slots the main planner workspace;
- separate planning into three purposeful views instead of making seven day tabs impersonate a weekly
  overview: Week shows the actual dishes across all seven days, Day is the focused editing surface,
  and Prep groups repeated recipes into total servings plus the dates and meal slots they cover;
- default the current week to today's date while keeping the full Week view as the entry point, so a
  person can orient to the whole plan before editing the meal that is relevant now;
- keep nutrition visible beside the meals as planning guidance, with whole-week nutrition remaining
  important without repeating a second macro dashboard: Week compares the average of days that
  actually contain meals with the daily guide, Day keeps detailed remaining amounts beside the food,
  and unfinished days are never presented as nutritional failure;
- allow meal planning to begin before someone enters numeric targets: the Week and Day views invite
  a nutrition guide without blocking recipe placement, while target-dependent suggestions still ask
  for a guide because their ranking cannot be honest without one. When a guide is later created, the
  existing plan adopts it and nutrition guidance becomes available without rebuilding the week;
- present an existing nutrition guide as a calm review state instead of a permanent form: energy and
  macros remain prominent planning inputs, editing is explicit, the energy-to-macro comparison updates
  while values change, and the save action appears only when there is something to save;
- translate snapshot coverage into a human planning state (for example, “Nutrition estimate
  incomplete”) and keep the exact status and source-coverage percentage behind a disclosure;
- remove timezone and immutable-snapshot implementation copy from the normal planning surface;
- replace repeated or permanent add forms with a slot-level `Add a recipe` action and a search-first
  recipe sheet, so the date and meal context are already decided before recipe browsing begins;
- render planned meals as image-led rows with servings and a compact nutrition contribution; keep
  moving, refreshing, and removal behind a single adjustment disclosure;
- when a recipe has no photo, use category-aware Cookfully editorial food art rather than a repeated
  generic pot icon or an invented photo of the exact dish. Real imported/uploaded imagery always wins;
  discovery cards then limit their visible evidence to serving count, calories, and protein so the
  food remains the foreground rather than a four-macro dashboard;
- replace the database-state filter with cooking-oriented views (all, ready to plan, needs
  attention, archived), while retaining honest nutrition status on each card;
- add sorting by recency, name, protein, or calories and optional grouping by planning readiness;
- defer tag, cuisine, time, dietary, occasion, and custom-cookbook filters until those metadata exist
  in the domain model. Inventing UI-only facets would create filters that cannot be trusted.
- make manual recipe creation feel like writing a recipe: title, yield, ingredients, and method lead;
  description, source, parser output, matching state, and conversion assumptions remain available
  through progressive disclosure instead of turning the primary task into a provenance form;
- keep Agent Access directly addressable for owners who need integrations, but remove it from everyday
  kitchen navigation because token administration is not part of planning, cooking, or shopping;
- make the grocery list read as the final meal-prep step—items left, check-off behavior, pantry use,
  and manual extras—while keeping ingredient provenance behind per-item disclosure.

Evidence: `frontend/src/app/App.tsx`, `frontend/src/features/plans/WeeklyPlannerPage.tsx`,
`frontend/src/features/plans/NutritionGuideInvitation.tsx`,
`frontend/src/features/plans/MealPlanEntry.tsx`, `frontend/src/features/plans/DayTabs.tsx`, and
`frontend/src/features/plans/RecipePickerSheet.tsx`,
`frontend/src/features/recipes/RecipeLibraryPage.tsx`, `frontend/src/features/recipes/RecipeEditorPage.tsx`,
`frontend/src/features/recipes/RecipeDetailPage.tsx`,
`frontend/src/features/suggestions/SuggestionPage.tsx`, and
`frontend/src/features/goals/GoalSettingsPage.tsx`,
`frontend/src/features/grocery/GroceryListPage.tsx`, and
`backend/src/cookfully/application/meal_plans.py`.

## A kitchen-first shell and direct-manipulation planner — 2026-08-20

### Problem being solved

Cookfully had capable recipe, planning, grocery, pantry, and nutrition workflows, but the app shell
gave too many destinations equal weight. The recipe editor also flattened ingredients and method into
two large text areas, while the weekly planner summarized meals more than it helped someone arrange
them. The combined effect felt administrative instead of like a contemporary cooking tool.

### Sources inspected

- [Mealie repository](https://github.com/mealie-recipes/mealie) and
  [Mealie feature documentation](https://docs.mealie.io/documentation/getting-started/features/) for
  the breadth of recipe organization, planning, shopping, and household capabilities;
- [Tandoor repository](https://github.com/TandoorRecipes/recipes) and
  [Tandoor documentation](https://docs.tandoor.dev/) for its powerful search, cookbook, meal-plan,
  shopping, and self-hosting model;
- [dnd-kit React quickstart](https://dndkit.com/react/quickstart) and
  [sensor guidance](https://dndkit.com/react/guides/sensors) for pointer and keyboard drag behavior;
- [React Router view-transition guide](https://reactrouter.com/how-to/view-transitions) and
  [MDN View Transition API](https://developer.mozilla.org/en-US/docs/Web/API/View_Transition_API)
  for progressive route transitions with reduced-motion fallback.
- the owner-selected Cookfully labelled-strip prototype for the exact app typography, warm canvas,
  112 px rail, compact dinner/week composition, radii, spacing, and restrained color rhythm.

### Benefits and liabilities observed

Mealie and Tandoor prove that a self-hosted recipe product can cover a broad kitchen workflow, but
their capability breadth also encourages taxonomy and administration to become prominent navigation.
That tradeoff fits power users better than Cookfully's default cooking-first path. Direct manipulation
is a strong fit for a weekly plan because the destination is spatially visible, but drag alone would
exclude keyboard users and anyone who finds precise dragging awkward. Route transitions can preserve
visual context between a recipe card and detail view, but generic page animation would add motion
without meaning and can conflict with reduced-motion preferences.

### Local decision

Adapt the capability, not the information density:

- make Home the post-login destination and keep permanent navigation to Home, Recipes, Plan,
  Grocery, and Pantry; move Foods, Goals, Settings, and agent access into utility locations;
- use the prototype's fixed 112 px labelled strip on desktop and tablet, with a labelled bottom bar
  on mobile so icons never have to carry meaning alone;
- treat the prototype's Afacad Flux 500 display type, Inclusive Sans 400 body type, warm canvas,
  compact two-card Home dashboard, and three-recipe shelf as the product-density reference;
- provide a focused command palette for navigation, recipe lookup, and common kitchen actions while
  keeping natural-language planning out of this iteration;
- reduce recipe-library competition to search, All/Favorites, a single Add recipe disclosure, and a
  secondary Refine disclosure; keep ideas contextual to Recipes, Home, and Plan;
- preserve ingredient text exactly while editing each ingredient as a reorderable row, disclose
  parsed amount/unit/food fields only when useful, and split multiline paste into rows with Undo;
- present method as separate reorderable step cards so the same structure remains readable in recipe
  detail and Cook Mode;
- let planned meals move between explicit day/slot targets with pointer or keyboard drag, announce
  movement to assistive technology, and always provide a Move dialog fallback;
- keep “Help fill this week” a guided preview-and-accept flow; suggestions never change the plan until
  the owner explicitly accepts selected meals;
- apply shared-element route transitions only to recipe media/title context, and remove transition
  animation when the operating system requests reduced motion;
- keep pantry recommendations evidence-based through match coverage and missing counts; do not invent
  expiry or “use soon” claims without a pantry-expiry domain model.

Evidence: `frontend/src/app/App.tsx`, `frontend/src/app/CommandPalette.tsx`,
`frontend/src/features/home/HomePage.tsx`, `frontend/src/features/recipes/RecipeLibraryPage.tsx`,
`frontend/src/features/recipes/RecipeEditorPage.tsx`,
`frontend/src/features/recipes/StructuredRecipeFields.tsx`,
`frontend/src/features/plans/WeekOverview.tsx`, `frontend/src/features/plans/MoveMealSheet.tsx`, and
`frontend/src/features/plans/WeeklyPlannerPage.tsx`.

## Persistent sessions and an administration surface — 2026-08-12

### Sources inspected

- [Immich auth service](https://github.com/immich-app/immich/blob/main/server/src/services/auth.service.ts)
  and [auth controller](https://github.com/immich-app/immich/blob/main/server/src/controllers/auth.controller.ts):
  `login` issues a 32-byte opaque token, SHA-256-hashed at rest in a `sessions` table; `validateSession`
  has no expiry check — a session is valid until deleted. `logout` and password change are the only
  revocation paths (password change invalidates other sessions).
- [Immich cookie utility](https://github.com/immich-app/immich/blob/main/server/src/utils/response.ts):
  `immich_access_token` is HttpOnly, `SameSite=lax`, with `maxAge` of 400 days (the browser cookie
  ceiling), plus a non-HttpOnly `immich_is_authenticated` hint cookie.
- [Immich user-management](https://immich.app/docs/administration/user-management),
  [system-settings](https://immich.app/docs/administration/system-settings), and
  [jobs-workers](https://immich.app/docs/administration/jobs-workers) documentation for the admin surface.

### Objective comparison

Immich's "stay signed in" behavior is not a client-side token trick: it is an opaque, server-side
session that simply does not expire, delivered in a persistent cookie, with revocation and a session
list as the compensating control. Cookfully already uses the same underlying mechanism (opaque token,
SHA-256 hashed, PostgreSQL-backed, HttpOnly cookie) but imposes a 14-day hard expiry, no session list,
no logout control, and no password change. The difference is therefore lifetime and the missing
revocation surface, not a fundamentally different auth model.

Immich's administration panel is justified by multi-tenancy: user creation, storage quotas, per-user
server stats, and a broad machine-learning/video configuration. Cookfully is deliberately single-owner
(constitution and spec FR-034), so none of that maps over. Filtering Immich's admin surfaces through
Cookfully's persona test ("does this help plan, cook, and eat better food with less friction?") leaves
only the account/security surface as genuinely useful — and that surface is forced once sessions become
long-lived, because revocation replaces expiry as the security control. Instance stats, a jobs page,
and a settings editor are operator tooling with no daily value for one owner who already knows their
library and edits `.env` for configuration.

### Local decision

Adopt Immich's session model and reject its administration panel:

- sessions last ~400 days by default (operator-configurable) and are valid until explicitly revoked;
  the browser cookie expiry mirrors the session expiry;
- a session list with a recognizable device label, sign-in and last-activity time, a current-session
  marker, and per-session revocation is the compensating control;
- a password-change endpoint invalidates all other sessions (Immich's `invalidateSessions` behavior);
- switch the session cookie from `SameSite=strict` to `lax` to match Immich and avoid showing the
  sign-in screen when the owner arrives from an external dashboard link, while the double-submit CSRF
  header still protects mutations;
- consolidate account and security controls into a single tabbed Settings page (Account, Security, API
  access) rather than an Immich-style administration panel, and give the currently-unlinked Agent Access
  page a home there (consistent with the earlier decision to keep Agent Access directly addressable but
  out of kitchen navigation);
- explicitly reject instance stats, background-job administration, and a database-backed settings
  editor for now; revisit only if the product grows multi-user or the owner reports needing server
  visibility.

Evidence is defined by `specs/002-persistent-sessions-settings/spec.md`. This decision should be
reconsidered if the product becomes multi-user, because resource ownership, quotas, and delegated
administration would then require the richer authorization model Immich already has.

## Responsive navigation and owner controls — 2026-08-12

### Sources inspected

- [Tandoor configuration documentation](https://docs.tandoor.dev/system/configuration/), which
  exposes extensive server, database, authentication, external-service, and debugging options for
  a power-user deployment
- [Immich search documentation](https://docs.immich.app/features/searching/), which keeps its
  high-dimensional search facets within an explicit search experience instead of the ordinary
  browsing flow
- [Mealie feature documentation](https://docs.mealie.io/), which keeps recipe, planning, and
  shopping capabilities central for household users

### Objective comparison

Tandoor's configuration breadth is appropriate for a mature, highly configurable Django service,
but it demonstrates the cost of putting operator concepts beside routine recipe work: a person
opening a food app must parse concerns such as database connection, proxy count, OAuth, debugging,
and AI-provider choices. Immich supports powerful search but makes advanced facets contextual to
finding assets rather than a permanent global form. Mealie's high-level feature framing is closer to
Cookfully's everyday scope, while still not providing a nutrition-first boundary between household
planning and owner administration.

Responsive navigation adds a second constraint. A mobile bottom bar provides comfortably labelled,
thumb-reachable destinations; carrying that full-width pattern into a tablet wastes vertical space
and makes a 768–1023px planner read like an enlarged phone. Conversely, a permanent desktop rail at
phone width would crowd recipe and planning content.

### Local decision

Historical note: the 80 px tablet-rail choice below was superseded by the owner-selected 112 px
labelled-strip prototype on 2026-08-20.

Adapt the clear hierarchy rather than copying any source UI:

- desktop retains labelled Kitchen and Your space navigation;
- tablets use a compact 80px icon rail with accessible text and hover labels, preserving canvas for
  recipes and the weekly plan;
- phones retain a labelled four-destination bottom bar and place Foods, Goals, and System under
  `More`;
- System exposes owner integration controls only from that deliberate secondary route, never as a
  cooking or planning destination.

Evidence: `frontend/src/app/App.tsx`, `frontend/src/styles/globals.css`, and the desktop/mobile
browser suite under `frontend/e2e/`. Revisit if actual owner behavior shows that a specific System
task is frequent enough to deserve a purpose-built, contextual entry point.

## First recipe to finished shop — 2026-08-13

### Problem being solved

Cookfully's planning foundation is strong, but a first-time owner still lands in a recipe library
that assumes they know the product's sequence. Manual recipes lack the visual recognition afforded
to imported recipes. Grocery work ends at individual checkboxes, without a lightweight way to order
the trip around real shopping stops or mark the weekly trip finished. Finally, the library has
planning-readiness views but no intentionally small layer for keeping personally trusted recipes
close at hand.

### Sources inspected

- [Mealie feature documentation](https://docs.mealie.io/documentation/getting-started/features/):
  categories, free-form tags, cookbooks, meal-type planner rules, linked shopping-list recipes, and
  reorderable shopping labels.
- [Tandoor shopping documentation](https://docs.tandoor.dev/features/shopping/): recipe- and
  meal-plan-derived shopping lists plus supermarket-specific ordering; Tandoor explicitly labels
  the shopping feature as work in progress.
- [Tandoor documentation](https://docs.tandoor.dev/): cookbooks, tags, recipe-focused management,
  and shopping lists attached to recipes or plans.
- [Immich quick start](https://docs.immich.app/overview/quick-start/) and
  [mobile backup](https://docs.immich.app/features/mobile-backup/): direct, status-visible media
  transfer, explicit album selection, and duplicate-safe media handling.

### Benefits and liabilities observed

Mealie proves that collections, meal-type organization, and labelled shopping lists help a recipe
library grow, but its separate categories, tags, tools, saved-search cookbooks, rules, label editor,
and batch surfaces ask an owner to model their whole kitchen before they can cook. Tandoor confirms
the practical value of generating shopping from recipes or meal plans and arranging it for a store,
but its feature remains explicitly unfinished and should not be copied as an ever-expanding shopping
configuration area. Immich makes uploads feel trustworthy through obvious progress and a distinction
between local and saved media; its asset-library scale, bulk backup, sharing, and album synchronization
are unnecessary for one representative recipe photo.

### Local decision

Adapt the useful hierarchy while rejecting metadata and administration sprawl:

- make first run a non-blocking choice of the next useful action, not a questionnaire or empty
  dashboard; the owner may start by writing/importing a recipe or seeing the week, and nutrition
  guidance remains optional;
- allow one optional, owner-controlled photo only for a manually created recipe. Show it consistently
  where recipe imagery already exists, use visible progress/recovery states, and never infer nutrition
  from it or force every recipe to look photographed;
- introduce owner-named shopping stops, an explicit unassigned fallback, and opt-in remembered
  placements for reliable repeated ingredients. Preserve the current plan-source, manual-edit,
  completion, and pantry-deduction contracts on refresh. Finishing a fully checked list is an
  intentional weekly-shop record, not a destructive clear action: it becomes read-only history
  until the owner explicitly reopens it;
- add favorites, named many-to-many collections, and the four standard meal roles. Keep them optional
  and progressively disclosed, with focused filters rather than a permanent tag-management page;
- reject arbitrary tags, cuisine/diet/occasion taxonomies, retailer catalogues, price tracking,
  delivery/checkout, multiple or step photos, bulk photo backup, sharing, and automatic AI
  categorization until user evidence establishes a specific need.

Evidence is defined by `specs/003-onboard-recipe-library/spec.md`. Revisit the organization model if
the app becomes shared or owners consistently need a type of retrieval that cannot be expressed by a
favorite, one collection, or one standard meal role.

## Import duplicate merge, draft preview, and image persistence — 2026-08-16

### Problem being solved

Importing the same source twice left the owner with either a silent duplicate or a destructive
overwrite decision. In-editor drafts could not be sanity-checked against the finished recipe
presentation before saving, and a PDF import's generated thumbnail was dropped at confirm time so
the saved recipe lost the image the owner had just approved.

### Sources inspected

- [Mealie recipe CRUD behavior](https://docs.mealie.io/documentation/getting-started/features/):
  recipes can be duplicated and updated, but Mealie keeps creation and editing as separate primary
  surfaces rather than a reviewed-import-then-replace flow.
- [Tandoor Recipes repository](https://github.com/TandoorRecipes/recipes): import/update handling and
  the ability to re-save a recipe while preserving the existing row's identity.
- [Immich asset handling](https://docs.immich.app/features/backup/): media is written
  asynchronously and survives retries, motivating best-effort, never-blocking persistence of an
  already-approved image.

### Benefits and liabilities observed

Mealie and Tandoor both show that a recipe's editable content and its stable identity (collections,
favorites, photo, source) are conceptually separate, and that replacing content on re-save is a
normal, recoverable operation rather than a delete-plus-recreate. Neither reference implements a
"merge imported content into the matching existing recipe" step from within an import review, and
both are multi-user systems where a destructive global overwrite would be riskier. Immich's
write-aside, retry-tolerant image pipeline supports attaching a chosen thumbnail after the recipe
exists instead of coupling image persistence to the parse transaction.

### Local decision

Adopt the identity/content split and adapt it to the single-owner, reviewed-import flow:

- detect probable duplicates during import preview by normalized title, return their id and content
  version, and offer a per-duplicate **Merge into existing** action that replaces content fields
  while preserving id, photo, collections, favorites, source URL, and description;
- keep merge as one explicit API call that reuses the existing update path with a stale-version
  guard, so a concurrent edit cannot be silently clobbered;
- attach a confirmed PDF thumbnail after save on a best-effort path that can never fail the import,
  and surface the attach explicitly in the confirm step;
- reject the destructive alternatives: automatic overwrite of the nearest match, silent duplication,
  or blocking the import on image storage.

Evidence is defined by the merge (`POST /recipes/import/merge`), attach
(`PUT /recipes/{recipeId}/photo/attach`), and version-gated `attach_url` contracts plus the import
dialog, editor Preview toggle, and E2E coverage. Revisit if the product becomes multi-user, where
duplicate resolution would need explicit per-owner confirmation and ownership checks.

## Instant recipe feedback, provenance, and thumbnail framing — 2026-08-16

### Problem being solved

Recipe imports, nutrition jobs, favorites, deletion, and image selection previously made important
state changes feel silent or technically opaque. A recipe could be usable while nutrition was still
being resolved, and a selected image could be stored without preserving the owner's preferred framing.

### Sources inspected

- [Mealie maintained repository](https://github.com/mealie-recipes/mealie) for recipe organization and
  import-oriented presentation patterns.
- [Tandoor Recipes maintained repository](https://github.com/TandoorRecipes/recipes) for collections,
  source metadata, and editable recipe identity.
- [Immich asset and trash documentation](https://docs.immich.app/features/trash/) for reversible
  destructive actions, durable media handling, and explicit recovery states.

### Benefits and liabilities observed

Collections and source context are useful retrieval aids in all three products, but their broader
taxonomies and asset workflows would add unnecessary configuration to Cookfully. Immich's explicit
trash boundary is safer than immediate erasure, but copying a large asset-management subsystem would
be disproportionate here. None of the references provides nutrition-stage progress with Cookfully's
serving-basis and coverage requirements.

### Local decision

Adapt the useful signals while keeping the nutrition-first scope narrow:

- show human-readable recipe job stages and bounded progress from the authoritative persisted job;
- make nutrition a visible result with coverage, basis, partial/manual states, and a path to review;
- use optimistic favorite, collection, archive, and delete feedback with rollback and a recoverable
  archived state when permanent deletion cannot finish;
- expose origin, source, and collection context without introducing arbitrary tags or taxonomies;
- store normalized focal-point and zoom metadata separately from original media, with keyboard-accessible
  range controls and CSS framing rather than destructive image rewriting.

Evidence is defined by the recipe crop/origin contract, `RecipeProcessingBanner`, nutrition overview,
collection strip, optimistic organization mutations, and focused Vitest coverage. Revisit these choices
if Cookfully becomes shared or gains a substantially larger media library.

## Home as the product-wide visual reference — 2026-08-20

### Problem being solved

The Home screen had become attractive but needed to carry the identity of the entire product. A screenshot
could communicate a mood, but it did not give implementation work a reusable contract for shell, type,
recipe media, nutrition, density, responsive behavior, or interaction quality.

### Sources inspected

- The live Cookfully Home route at `http://localhost:5173/app`, including its DOM boxes and computed
  styles at a 1734×1272 desktop viewport.
- The current Cookfully Home implementation and shared components: `HomePage`, `RecipeMetadata`,
  `RecipeFallbackArt`, `KitchenCompanion`, `CommandPalette`, and the responsive shell.
- The earlier visual review in `critique-UI.md`, plus the product requirements in `Law_of_UX.md` and
  `nutrition-recipe-app-spec.md`.
- Mealie, Tandoor, and Immich as recurring comparison points for ownership and practical flows, not as
  visual authorities.

### Benefits and liabilities observed

The live Home composition provides a strong product signature: a quiet 112px rail; 38px Afacad Flux
greeting; wide editorial Tonight hero; compact This week card; pale-mint Use soon; separator-led Quick
actions; contextual Cook next recommendations; compact Recently saved shelf; and dark herb Grocery prompt.
Food imagery is integrated into the hero rather than stitched into a small circular widget. Recipe cards
share media and metadata contracts, while nutrition colors communicate category without turning the app
into a rainbow dashboard.

The liability is that a strong reference can become a collection of one-off CSS if it is copied by eye.
The asymmetric corners, dense module sequence, and food-led contrast must therefore be expressed as shared
tokens and components. Mobile also cannot be inferred by simply stacking the desktop grid; fixed navigation,
touch targets, and cooking context need their own composition.

### Local decision

Adopt Home as the product-wide visual source of truth and codify it in `DESIGN.md`, `.impeccable.md`,
`Law_of_UX.md`, and `critique-UI.md`:

- use the warm ivory/herb/mint/saffron palette, Afacad Flux + Inclusive Sans typography, 4px rhythm,
  10px controls, 18px surfaces, 22px media, and restrained organic asymmetry globally;
- reuse `KitchenShell`, `PageIntro`, `EditorialHero`, `WeekCard`, `UseSoon`, `QuickActions`, recipe
  media/fallback art, `RecipeCard`/`RecipeShelf`, `RecipeMetadata`/`NutritionRibbon`, and state helpers;
- keep food before figures while showing time, servings, calories, protein, carbs, and fat wherever a
  recipe appears, with honest missing/coverage/manual/stale states;
- preserve Home's density and question order, while letting Recipes, Plan, Pantry, Grocery, Cook mode,
  and Settings adapt the pattern to their own task;
- keep Mealie/Tandoor's useful ownership and organization ideas, reject their dated/dense presentation,
  and use Immich's self-hosted polish and resilient processing as an architectural bar;
- validate every route against Home at 1440×900 and 390×844, including keyboard, reduced motion, safe
  areas, focus, and real loading/empty/error states.

The Home reference is deliberately adopted rather than copied from any external product. Revisit the
decision only through a new live review and update all four context documents together.

## Structured recipe capture — 2026-08-20

### Problem being solved

The earlier editor technically replaced freeform ingredient and instruction textareas, but still behaved
like an implementation workbench: every concern appeared at once, the reading order was unclear, and a
phone user could switch sections without being guided to the next useful piece of the recipe. A recipe
editor should help someone preserve the way they cook, not make them complete a data-entry checklist.

### Sources inspected

- [Mealie's current ingredient editor](https://github.com/mealie-recipes/mealie/blob/mealie-next/frontend/app/components/Domain/Recipe/RecipeIngredientEditor.vue), which uses an explicit recipe-section title plus distinct quantity, unit, food, and note controls.
- [Mealie's current recipe service](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/services/recipe/recipe_service.py), which creates a starter ingredient and an ordered starter instruction for a new manual recipe.
- [Tandoor's current documentation](https://docs.tandoor.dev/), which describes its editor as fast and intuitive while its broader product also exposes large power-user organization surfaces.
- [Tandoor's FAQ](https://docs.tandoor.dev/faq/), which documents a temporary markdown-editor preview whose rendering can differ from the finished recipe.

### Benefits and liabilities observed

Mealie confirms that ingredients and instructions deserve independent, ordered controls and that a blank
starter row makes a manual recipe immediately actionable. Its compact quantity/unit/food layout is useful
for structured data but would make Cookfully's preserved original ingredient text feel overly technical if
shown by default. Tandoor validates a fast editor for serious cooks, but its large configurable surface and
markdown-preview mismatch are the opposite of a calm, trustworthy capture experience.

### Local decision

Adopt the useful structured-entry principles while rejecting their density and preview compromises:

- organize editing as a visible four-part journey: Recipe, Ingredients, Method, and Finish; desktop keeps
  the journey as orientation, while mobile makes it the active single-section flow with explicit next and
  previous controls;
- preserve one complete original ingredient line as the primary row, with parsed amount, unit, food,
  preparation, and optionality disclosed only when useful; multiline pastes still become individual rows;
- keep method steps as numbered, independently editable units so they map directly to Cook Mode;
- keep the Cookfully draft preview as the same recipe presentation used by reading surfaces, never a
  separate markdown rendering path;
- make cover, source, description, and manual nutrition a quiet Finish step. They are meaningful, but
  never requirements for saving a recipe.

This approach fits Cookfully's cooking-first scope: structured enough to plan and calculate honestly, but
still generous to a person typing a family recipe from memory. Revisit only if direct usability evidence
shows a materially faster capture model without losing readable, durable recipe structure.

## Settings jobs — 2026-08-21

### Problem being solved

Background work was visible only as incidental progress on individual screens. Owners needed one calm
place to restart recipe processing, repair missing nutrition data, install reference releases, and prepare
portable exports without turning Settings into an operations console.

### Sources inspected

- Immich's Job Queues screen supplied by the owner as a visual reference: one queue card per job, active and
  waiting counts, and explicit all/missing or rescan actions.
- Cookfully's existing recipe recalculation, reference-data install, job polling, and portable-export
  contracts, so every action in the new screen maps to a real endpoint.

### Benefits and liabilities observed

Immich's split card/action grammar makes queue state legible and gives recovery actions a predictable home.
Its dark, infrastructure-first presentation would make Cookfully feel like a server console, and its broad
asset vocabulary does not map cleanly to recipes or nutrition releases.

### Local decision

Adapt the queue grammar, not the visual skin: use warm Cookfully surfaces, organic corners, shared Button and
SectionHeading primitives, three honest queue metrics, and a compact action rail. Recipe processing supports
Run all and Run missing only through existing per-recipe recalculation; reference data exposes refresh and
missing-release install; portable export is a single media-inclusive action. Keep the page inside Settings,
poll only while a job is active, and explain that re-runs preserve manual nutrition corrections.

## Model-only intelligence service — 2026-08-21

### Problem being solved

Needle 2 needs a local runtime boundary without moving Cookfully's application coordination, durable jobs,
or authoritative data out of the backend.

### Source inspected

- [Immich's production Compose service](https://github.com/immich-app/immich/blob/main/docker/docker-compose.prod.yml),
  which separates the machine-learning service and model cache from the server and database.

### Local decision

Adopt the isolation boundary, not Immich's application responsibilities: Cookfully adds one private
model-only `intelligence` container. The API and existing worker call it over an authenticated internal
HTTP protocol; they retain all owner resolution, job scheduling, retries, persistence, and mutation
coordination. The model container receives schemas and text only, has no Postgres or Redis credentials,
and may later run on a trusted LAN host through a configured HTTPS URL. No cloud inference fallback is
allowed.

Compose also places the model service on a private network shared only with the API and worker;
Postgres and Redis are not attached to that network. This makes the model-only boundary a deployment
property as well as an application contract.


## Thumbnail crop editor — 2026-08-22

### Problem being solved

Thumbnail framing was stored as focal-point/zoom metadata interpreted independently by each surface
(card, hero, home tiles), so the editor preview drifted from what actually rendered and framing was not
WYSIWYG.

### Source inspected

- [Immich asset crop/focus editing](https://docs.immich.app/features/automatic-backup) and its web client
  crop editor: a contained image preview with the exterior dimmed, aspect-locked corner-handle resizing,
  and a reset-to-fit action.

### Benefits and liabilities observed

Immich's contained editor captures exact user intent and renders predictably everywhere the same rect is
used; the dimmed exterior makes the kept region unambiguous. Liabilities: the server trusts client
geometry without validating composition quality, and because no pixel derivatives are generated, large
originals are downloaded in full and cropped client-side on every render.

### Local decision

Adopt the interaction pattern, adapted to Cookfully's contract: a normalized `{x,y,width,height}` rect
persisted as exact decimals beside the original media (migration 0026 replaced focal/zoom columns), never
rewriting the original image. Reject backend derivative generation for now — it would add storage,
cache invalidation, and media-pipeline complexity that this project's single-owner scale does not justify;
client-side cropping from exact-decimal rects is deterministic across surfaces. Evidence:
`backend/src/cookfully/api/schemas/recipes.py` (`ThumbnailCropRequest` bounds validation),
`backend/migrations/versions/0026_recipe_thumbnail_crop_rect.py`, and the frontend `RecipeMedia` crop-var
tests.

## Ingredient & Nutrition Engine — P1 matching unification — 2026-08-22

### Problem being solved

Ingredient matching, normalization, and embedder policy were implemented separately per surface: pantry used a `difflib.SequenceMatcher` ratio (`application/pantry.py:118`), while recipe ingredients and the Foods picker shared the signal-based `FoodMatcher` with divergent embedder factories in `api/routes/foods.py:56` and `jobs/recipe_pipeline.py:446`. Behavior drifted per surface and only pantry surfaced its confidence as the Review-match chip. A planned default to the neural embedding model lacked a single place to enforce it.

### Sources inspected

- The live repository inventory of the current matching stack (phase-0 explore): `domain/ingredient_nutrition/matching.py` signals, `food_semantics` profiles, `semantic_embeddings` Hashing vs FastEmbed paths, `nutrition_intelligence` settings singleton, and the pantry/foods/pipeline call sites.
- [Mealie matching](https://github.com/mealie-recipes/mealie/blob/mealie-next/mealie/services/matching.py) and [Tandoor ingredient parsing](https://github.com/TandoorRecipes/recipes/blob/develop/cookbook/helper/ingredient_parser.py) as previously recorded — both match against the user's small curated list, not a large USDA corpus, so neither justifies silent single-best matching for pantry use.

### Objective comparison

Scattered matchers let each surface evolve independently, but at this product's scale they produce conflicting confidences and statuses for the same input text. Copying a separately deployed matching microservice would add deployment/network complexity with no scaling benefit for a single-owner self-hosted app. A single in-process domain module with one embedder factory preserves uniform behavior and keeps the existing background-job and authoritative-DB contracts intact.

### Local decision

Adopt a single in-process **Ingredient & Nutrition Engine** boundary, not a deployed microservice:

- `domain/ingredient_nutrition/{matching,normalization}.py` is the sole owner of matching signals/normalization; `application/ingredient_engine.py` (`IngredientEngine`) is the only facade routes/jobs may import — enforced by an architecture test.
- All three existing consumers (pantry auto-match, Foods search picker, recipe ingredient pipeline) route through the engine; pantry's `proposed` status now maps from the shared `ambiguous` band so the Review-match chip is the same scorer as everywhere else.
- The engine is the sole reader of `NutritionIntelligenceSettings`; background paths fall back to hashing when the model is not ready, while interactive settings flows keep explicit 409/503 readiness signals.
- `fastembed` becomes the persisted default (`backend = 'fastembed'`, model `BAAI/bge-small-en-v1.5`) via migration `0027_default_neural_matching.py` and a `fastembed` column default; existing `hashing` rows are migrated.

Rejected: keeping per-surface matchers or extracting a network microservice in P1. Deferred: normalization consolidation (P2), quantity/owner-serving deduplication (P3), and nutrition-data lookup/computation consolidation (P4) per the spec's phasing.

Evidence: `backend/src/cookfully/application/ingredient_engine.py`, the moved `domain/ingredient_nutrition` package, `backend/migrations/versions/0027_default_neural_matching.py`, `backend/tests/unit/test_ingredient_engine.py` + `test_ingredient_engine_boundary.py`, and the updated `backend/tests/unit/test_pantry.py` mapping the engine's decisions to pantry statuses.

## Cold delivery, staged media, and job isolation — 2026-08-25

### Problem being solved

The kitchen interface should feel immediate on modest self-hosted hardware. The previous path could
send a multi-megabyte hero/original image, fan out Home requests, and let bulk indexing contend with
interactive imports and saves.

### Sources inspected

- [Immich system settings](https://docs.immich.app/administration/system-settings/) documents that
  image variants trade CPU and storage for lower delivery cost, and that raising job concurrency does
  not make an individual job faster and can reduce API responsiveness.
- [Immich jobs and workers](https://docs.immich.app/administration/jobs-workers/) documents separating
  worker responsibilities so background processing can be scheduled independently of the API.

### Benefits and liabilities observed

Pre-generated variants make common renders substantially cheaper, and distinct worker queues prevent a
bulk backlog from blocking a small interactive action. Both patterns can become expensive if every
original produces many sizes, if previews never expire, or if separation is implemented by simply
adding more concurrent workers.

### Local decision

Adapt the bounded parts of the pattern: generate only a 480px card and 960px reading WebP for a newly
selected photo, stage them for one hour while the user is editing, and delete expired photo stages and
import previews in retention. Browser `srcset` selects the card variant where appropriate. Keep a total
worker concurrency of four by splitting it into two interactive and two bulk slots rather than adding
capacity; interactive jobs therefore retain priority without requiring a larger server. Reject a third
image derivative, original-image delivery for normal screens, indefinite preview retention, and loading
the semantic model into the interactive queue. Evidence: `recipe_images.py`, `recipe_photos.py`,
`jobs/outbox_process.py`, and the compose worker definitions.
