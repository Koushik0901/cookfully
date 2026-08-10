# Feature Specification: Gym-Focused Recipe & Nutrition Planner

**Feature Branch**: `001-nutrition-recipe-planner`  
**Created**: 2026-08-09  
**Status**: In implementation  
**Input**: User description: "Create the product specification from nutrition-recipe-app-spec.md"

## Clarifications

### Session 2026-08-09

- Q: What benchmark policy should gate P1? → A: Use a fixed, versioned 50-recipe stratified corpus with a 30-recipe primary release subset and 20 extension/stress cases; require all four core macros plus at least 90% ingredient coverage, and use qualified published references with threshold-aware error calculations.
- Q: What numeric precision and rounding policy should the product use? → A: Store nutrients and ingredient quantities to six decimal places and servings to three, serialize public decimals as strings, use round-half-up, display calories to 1 kcal and macros to 0.1 g, and aggregate the same display-quantized plan-entry values.
- Q: What should happen when recipes are archived, restored, or permanently deleted? → A: Archive is reversible and removes a recipe from active use; restore returns it to its prior usable state or marks nutrition stale; confirmed permanent deletion is limited to archived recipes, cancels active jobs, removes recipe-owned data, and preserves detached historical snapshots and provenance.
- Q: What retention policy should apply to imported content, provider data, diagnostics, and audit history? → A: Discard successful-import HTML after extraction; permit encrypted failed-import HTML for 24 hours only with owner-enabled diagnostics; never retain raw provider requests or responses; retain detailed job diagnostics for 30 days then safe codes and timestamps for one year; retain estimates and corrections until owner erasure; let backup rotation govern residual copies while an independent content-free erasure ledger prevents restored backups from resurrecting erased data.
- Q: How should import and nutrition jobs acknowledge, retry, and communicate completion? → A: Persist and acknowledge within one second, discover status by polling every two seconds on visible job screens and every 15 seconds elsewhere, time out attempts after 60 seconds, retry after 5 seconds, 30 seconds, 2 minutes, and 5 minutes for at most five attempts, and reach a visible terminal state within 15 minutes.

### Session 2026-08-10

- Q: How must full owner erasure work? → A: Provide an offline operator CLI that requires the instance to be stopped, the owner identifier, and an exact destructive confirmation; erase the owner account and every owner-controlled core, expansion, media, token, session, diagnostic, export, and job record, append an independent `owner_owned` ledger record, and return the instance to bootstrap state without allowing an older backup to resurrect erased data.
- Q: What environment defines reference-hardware performance results? → A: Use a Linux x86-64 Docker host limited to 4 vCPU, 8 GiB RAM, and SSD storage, with API, worker, PostgreSQL, and Redis on the same host; seed the documented dataset, warm each path with 10 unmeasured requests, then report p50/p95/max over at least 100 measured requests in each of three runs.
- Q: How are closest infeasible meal suggestions ranked? → A: Never violate recipe exclusions; first minimize the number of other unmet constraints, then minimize a normalized weighted distance using calories 4, protein 3, carbohydrates 1, fat 1, repetition 2, and missing required recipes 5, followed by fewer entries and lexicographic recipe-ID tie-breaks.
- Q: Which micronutrients does P6 support initially? → A: Support dietary fiber, sodium, potassium, calcium, iron, magnesium, vitamin D, vitamin B12, and vitamin C with canonical USDA nutrient mappings and units, while preserving null as unavailable rather than zero.
- Q: How are planning-aid framing and optional-provider degradation proven? → A: Label estimated nutrition and suggestion surfaces as planning aids rather than medical advice, describe the same limitation in API/MCP/export documentation, and run provider-disabled and forced-provider-failure fixtures proving manual recipe, nutrition, goal, plan, grocery, backup, and export workflows remain usable.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Capture Recipes With Actionable Nutrition (Priority: P1)

As a person tracking body composition, I want to create a recipe manually or import one from a web
page and receive a clear per-serving calorie and macro estimate so that every saved recipe is useful
for planning, even when the source provides no nutrition facts.

**Why this priority**: Reliable recipe capture and best-effort nutrition are the foundation for every
goal-aware workflow and the primary gap in existing recipe managers.

**Independent Test**: Create one recipe manually and import another from a representative public web
page, then verify that both retain their cooking information and reach either a complete nutrition
result or a specific, recoverable processing state.

**Acceptance Scenarios**:

1. **Given** a supported public recipe page, **When** the user imports its address, **Then** the saved
   recipe contains the available title, image, servings, ingredients, and instructions without manual
   transcription.
2. **Given** a recipe whose source has no nutrition facts, **When** nutrition processing completes,
   **Then** the user sees per-serving calories, protein, carbohydrates, and fat marked as estimated.
3. **Given** a recipe with source-provided nutrition, **When** it is saved, **Then** the displayed
   values identify their source and are not mislabeled as calculated values.
4. **Given** an incorrect automated value, **When** the user replaces it manually, **Then** the
   correction is labeled, retained, and used in every downstream total until the user resets it.
5. **Given** incomplete or failed processing, **When** the user views the recipe, **Then** the recipe
   remains editable and the missing or uncertain result, progress or retry timing, safe failure code,
   and explicit retry action are shown; reloading the application resumes status discovery.
6. **Given** an archived recipe, **When** the user restores or permanently deletes it, **Then** restore
   returns it to its prior usable state or a visible stale state, while confirmed deletion removes the
   recipe without changing historical plan totals or grocery provenance.
7. **Given** estimated nutrition, **When** the user reviews or acts on it, **Then** the relevant recipe,
   planning, and suggestion surface identifies it as a planning aid rather than medical advice without
   obscuring provenance, uncertainty, or correction controls.

---

### User Story 2 - Plan a Week Against Personal Targets (Priority: P2)

As a person cutting, bulking, or maintaining, I want to set calorie and macro targets and place
servings of saved recipes into a weekly plan so that I can see whether each meal, day, and week fits
my goal.

**Why this priority**: Connecting recipes to personal targets turns a nutrition-aware recipe library
into the focused planning tool described by the product vision.

**Independent Test**: Using a seeded set of recipes with known nutrition, create a target profile,
fill a seven-day plan, change serving quantities, and verify all meal, day, and week comparisons.

**Acceptance Scenarios**:

1. **Given** maintenance energy and a cutting, bulking, or maintenance goal, **When** the user saves a
   target profile, **Then** the daily calorie and protein, carbohydrate, and fat targets are visible
   and editable.
2. **Given** saved recipes, **When** the user assigns recipe servings to dated meal slots, **Then** the
   plan shows the entries in the selected slots and preserves their serving quantities.
3. **Given** a populated plan, **When** an entry or serving quantity changes, **Then** meal, daily, and
   weekly totals and differences from target update consistently.
4. **Given** totals containing estimated and corrected values, **When** the user reviews progress,
   **Then** the interface distinguishes their data status without relying on color alone.
5. **Given** optional per-meal targets, **When** they are enabled, **Then** each meal comparison uses
   those targets while daily and weekly comparisons continue to use the overall profile.

---

### User Story 3 - Turn the Plan Into a Grocery List (Priority: P3)

As a weekly meal planner, I want one consolidated grocery list generated from planned servings so
that I can shop without manually copying and combining every recipe ingredient.

**Why this priority**: The grocery list closes the loop between planning and cooking and provides
immediate practical value from an otherwise complete weekly plan.

**Independent Test**: Generate a list from a known weekly plan containing repeated ingredients,
compatible and incompatible units, optional lines, and changed serving counts; compare the result
with a hand-calculated expected list.

**Acceptance Scenarios**:

1. **Given** repeated equivalent ingredients across planned recipes, **When** the list is generated,
   **Then** compatible quantities are combined and the contributing recipes remain traceable.
2. **Given** quantities that cannot be converted safely, **When** the list is generated, **Then** they
   remain separate rather than being combined incorrectly.
3. **Given** a changed plan or serving count, **When** the user refreshes the list, **Then** quantities
   reflect the current plan without silently discarding manual completion state.
4. **Given** a generated list, **When** the user checks off or edits an item, **Then** the shopping
   state is retained without changing the underlying recipe.

---

### User Story 4 - Receive Goal-Aware Meal Suggestions (Priority: P4)

As a user with a recipe library, I want meal suggestions that fit my remaining calorie and macro
budget with reasonable variety so that I can build a feasible plan faster.

**Why this priority**: Suggestions deliver the deeper goal-aware value of the product, but depend on
a trustworthy recipe library, nutrition estimates, goals, and meal planning already being available.

**Independent Test**: Seed recipes with known nutrition, define a target and variety limits, request
day and week suggestions for feasible and infeasible cases, and verify target fit and explanations.

**Acceptance Scenarios**:

1. **Given** an incomplete day with a feasible remaining budget, **When** the user requests options,
   **Then** suggested recipes fit the selected tolerances and show their effect on the day's totals.
2. **Given** a weekly request and sufficient variety, **When** suggestions are generated, **Then** the
   result respects the user's repetition limit.
3. **Given** no combination that meets every constraint, **When** suggestions are requested, **Then**
   the user receives the closest useful alternatives and a clear account of unmet constraints.
4. **Given** a suggestion, **When** the user accepts it, **Then** the selected servings are added to the
   plan and totals match the preview.

---

### User Story 5 - Use Core Data Through External Tools (Priority: P5)

As a user of a personal automation agent, I want documented structured access to my goals, recipes,
plans, totals, and grocery list so that external tools can reason and act without an in-app chatbot.

**Why this priority**: External access prevents a data silo and enables advanced personal workflows,
while the visual application remains a focused tool rather than a conversational interface.

**Independent Test**: Through the supported external interface, read a target profile and weekly
totals, find recipes by macro constraints, add a recipe serving to the plan, and retrieve the updated
grocery list; verify the visual application shows the same state.

**Acceptance Scenarios**:

1. **Given** an authorized external tool, **When** it reads goals, recipes, totals, or grocery items,
   **Then** it receives the same values, serving bases, and estimation states shown to the user.
2. **Given** a valid external request to change the meal plan, **When** it is accepted, **Then** the
   same validation and total calculations used by the visual application are applied.
3. **Given** an invalid or unavailable optional processing service, **When** an external action is
   attempted, **Then** the caller receives a specific failure without corrupting stored data.
4. **Given** a manually corrected nutrition value, **When** an external tool reads or uses the recipe,
   **Then** the correction takes precedence exactly as it does in the visual application.

---

### User Story 6 - Plan From Available Food and Richer Nutrition (Priority: P6)

As a user managing food at home, I want to record pantry items, find recipes that use them, and review
available micronutrients so that I can reduce waste and make more informed meal choices.

**Why this priority**: Pantry search and micronutrients extend the core planning loop but are not
required to prove the initial calorie-and-macro-focused product.

**Independent Test**: Record a small pantry, search against a seeded recipe library, and inspect
micronutrients for recipes with complete, partial, and unavailable reference data.

**Acceptance Scenarios**:

1. **Given** recorded pantry items, **When** the user searches for meals, **Then** results identify
   recipes that can be made fully or partially and list important missing ingredients.
2. **Given** a planned grocery list and pantry quantities, **When** pantry subtraction is enabled,
   **Then** only safely matched available amounts are deducted and every deduction is visible.
3. **Given** supported micronutrient data, **When** the user views a recipe or plan, **Then** available
   values are shown with the same provenance and estimation honesty as macros.
4. **Given** incomplete reference data, **When** micronutrients are displayed, **Then** missing values
   remain unknown rather than being presented as zero.

### Edge Cases

- A recipe page is unreachable, private, malformed, unsupported, or changes during import.
- A recipe has no serving count, non-numeric quantities, ranges, optional ingredients, ingredients
  without amounts, or instructions embedded in ingredient lines.
- Two food names are similar but nutritionally different, or no sufficiently reliable reference match
  exists.
- A unit is volume-based but the ingredient needs a density assumption for weight conversion.
- The user changes the recipe yield after an estimate or manual correction exists.
- Source nutrition conflicts with the ingredient-derived estimate or describes the full recipe rather
  than one serving.
- Processing times out, is retried, completes twice, or becomes unavailable after a recipe is saved.
- A target profile contains impossible, contradictory, zero, or negative values.
- A plan crosses a daylight-saving or timezone boundary, or the user's preferred first day of week
  changes.
- Archiving a recipe while processing is active, restoring it after its inputs or reference release
  changed, or permanently deleting a recipe referenced by current or historical plans.
- Grocery items have equivalent names with compatible units, equivalent names with incompatible
  units, or distinct foods with deceptively similar names.
- The recipe library is too small or nutritionally unsuitable to satisfy suggestion constraints.
- An external tool repeats a write request, submits stale data, or attempts an unsupported action.
- Backup, export, or restore occurs while nutrition processing or plan changes are in progress.
- Retention cleanup runs while a failed import is being inspected, owner erasure occurs while backups
  still contain an older snapshot, or diagnostic mode is disabled before its 24-hour expiry.
- An optional provider is disabled, unreachable, returns invalid structured output, or fails while the
  owner is editing recipes, entering manual nutrition, planning, shopping, backing up, or exporting.
- Full owner erasure is requested while the application is running, the confirmation does not exactly
  match, the independent ledger is unavailable, or a staged restore predates the erasure.

## Constitution Alignment *(mandatory)*

- **Macro-goal contribution**: The feature is centered on converting real recipes into calorie- and
  macro-aware day and week plans. Pantry and micronutrient expansion remains subordinate to that loop.
- **Nutrition and estimation impact**: Every recipe carries a per-serving status, source, assumptions,
  and calories, protein, carbohydrates, and fat after successful processing. Estimated, source-provided,
  partial, failed, and manually corrected states are visible; corrections remain authoritative until
  explicitly reset.
- **Structured processing**: Automated parsing and matching are finite structured tasks, may complete
  after the recipe is saved, must tolerate safe retries, and reuse results while recipe inputs remain
  unchanged. Meal suggestions solve explicit targets and constraints rather than use open-ended chat.
- **Data and agent access**: Recipes, nutrition, goals, plans, totals, and grocery lists use one
  consistent set of rules across the visual application and documented external access. Optional
  provider failures do not block manual workflows. Users can back up and export their data.
- **Reuse and experience**: Planning must evaluate established recipe import, ingredient parsing, and
  food-reference solutions before building equivalents. The experience follows `DESIGN.md`, supports
  desktop and narrow mobile use, and explicitly covers loading, empty, partial, estimated, and failure
  states with accessible non-color cues.
- **Explicit non-goals**: In-app chat, photo-based nutrition recognition, social/community features,
  broad recipe taxonomy for its own sake, a subscription-only service, medical nutrition advice, and
  unrestricted multi-tenant administration are excluded.

## Requirements *(mandatory)*

### Functional Requirements

#### Core Product Scope (P1-P3)

- **FR-001**: Users MUST be able to create, view, edit, archive, restore, and permanently delete recipes
  manually. Archive MUST be reversible and remove the recipe from normal search, new planning, and
  suggestions. Restore MUST return the recipe to its prior usable state when its active estimate still
  matches its inputs, otherwise it MUST expose a stale state and recovery action. Permanent deletion
  MUST require explicit confirmation and an archived recipe, cancel or supersede active jobs, remove
  recipe-owned ingredients, estimates, corrections, and unshared media, and detach rather than alter
  immutable historical plan snapshots and grocery provenance.
- **FR-002**: Users MUST be able to import a recipe from a public web address and review the captured
  title, image, yield, ingredients, and instructions before or after saving.
- **FR-003**: The system MUST preserve each original ingredient line and an editable structured
  interpretation containing, when present, quantity, unit, and food identity. Stored ingredient
  quantities MUST use fixed-decimal values with six fractional places.
- **FR-004**: Every active recipe MUST reach either a per-serving calorie, protein, carbohydrate, and
  fat result or an explicit partial or failed state with a recovery action.
- **FR-005**: Nutrition values MUST distinguish source-provided, estimated, and manually corrected
  data and retain their source, serving basis, assumptions, and last calculation time. Stored nutrient
  values MUST use fixed decimals with six fractional places, stored servings MUST use three fractional
  places, and public API/export decimal values MUST serialize as decimal strings rather than binary
  floating-point numbers. Before the P1 release, supported USDA FoodData Central Foundation Foods and
  SR Legacy releases MUST both be installed and active for automated reference matching. The product
  MUST expose each active release identifier, release date, source, attribution, and license; provide
  an operator-driven check, import, and explicit activation workflow; and document a review cadence of
  at least once every 90 days. A different release MUST NOT activate silently or rewrite existing
  estimates. When a required dataset is absent, automated reference matching MUST be visibly
  unavailable while source-provided nutrition, manual nutrition, and recipe editing remain usable.
- **FR-006**: Users MUST be able to review and correct ingredient matches, quantities, unit
  conversions, serving yield, and final nutrition values.
- **FR-007**: Manual corrections MUST take precedence in recipe displays, plan totals, suggestions,
  grocery calculations where applicable, and external reads until the user explicitly resets them.
- **FR-008**: Reprocessing MUST NOT overwrite a manual correction or duplicate a previously completed
  result for unchanged recipe inputs.
- **FR-009**: Changing a recipe yield or ingredient MUST clearly identify which calculated values are
  stale and require recalculation without silently changing historical plan entries. Restoring a
  recipe after nutrition-relevant inputs or reference data have changed MUST apply the same stale-state
  rule.
- **FR-010**: Users MUST be able to record maintenance energy, a daily calorie target, and daily
  protein, carbohydrate, and fat targets for cutting, bulking, or maintaining.
- **FR-011**: Users MUST be able to define optional targets for individual meal slots without losing
  the overall daily target.
- **FR-012**: Users MUST be able to add, move, copy, resize, and remove recipe servings in dated meal
  slots across a weekly plan.
- **FR-013**: The system MUST display calorie and macro totals and differences from target for each
  meal, day, and week, with visible indication when totals include estimated or incomplete data.
  Round-half-up MUST be used throughout. Plan entries MUST be quantized to whole kilocalories and
  0.1-gram macros before aggregation, and totals and target differences MUST aggregate those same
  quantized values so every displayed sum is exact and transport-independent.
- **FR-014**: Historical plan entries MUST preserve the nutrition basis used at the time or clearly
  notify the user before recalculation changes historical totals. Archive, restore, or permanent
  deletion of the referenced recipe MUST NOT mutate those immutable snapshots; permanent deletion
  retains detached recipe-title and grocery-source text required to interpret the history.
- **FR-015**: Users MUST be able to generate a grocery list from the current weekly plan and regenerate
  it after plan changes.
- **FR-016**: Grocery generation MUST scale ingredients by planned servings, combine only safely
  equivalent ingredients and units, keep unsafe combinations separate, and identify source recipes.
- **FR-017**: Users MUST be able to edit, add, remove, and check off grocery items without changing
  recipe definitions.
- **FR-018**: The system MUST preserve grocery completion and manual-edit state when refreshing the
  generated list unless a directly affected item requires user review.
- **FR-019**: Users MUST be able to back up and export recipes, nutrition provenance and corrections,
  goals, plans, and grocery data in documented, portable forms.
- **FR-020**: Optional automated processing failures MUST NOT prevent recipe editing, manual nutrition
  entry, goal management, meal planning, grocery use, backup, or export. Provider-disabled and forced-
  failure validation MUST exercise each of those workflows without a provider call or corrupt state.

#### Expansion Scope (P4-P6)

- **FR-021**: Users MUST be able to request recipe suggestions for the remaining calorie and macro
  budget of a meal, day, or week using selected target tolerances.
- **FR-022**: Users MUST be able to set variety constraints, exclusions, required recipes, and maximum
  repetition for suggestions.
- **FR-023**: When no suggestion satisfies every constraint, the system MUST show the closest useful
  alternatives and identify the constraints each alternative misses. Recipe exclusions MUST remain
  hard constraints. Alternatives MUST first minimize the number of other unmet constraints, then a
  normalized weighted distance using weights of 4 for calories, 3 for protein, 1 for carbohydrates,
  1 for fat, 2 for repetition overage, and 5 for each missing required recipe; ties MUST prefer fewer
  entries and then lexicographically ordered recipe identifiers so results are deterministic.
- **FR-024**: Users MUST be able to preview a suggestion's target impact and accept all or part of it
  into the meal plan without totals changing from the preview.
- **FR-025**: Authorized external tools MUST be able to read goals, recipe nutrition and provenance,
  meal plans, meal/day/week totals, and grocery lists through a documented structured interface.
- **FR-026**: Authorized external tools MUST be able to find recipes by calorie and macro constraints
  and add, move, resize, or remove meal-plan entries using the same rules as the visual application.
- **FR-027**: Repeated or stale external write requests MUST be detected so they cannot create silent
  duplicate entries or overwrite newer changes without a conflict response.
- **FR-028**: Users MUST be able to record pantry items and quantities and search for recipes based on
  what is fully or partially available.
- **FR-029**: Pantry deductions from grocery lists MUST occur only for safely matched items and MUST
  remain visible and reversible.
- **FR-030**: The system MUST display supported micronutrients while distinguishing unavailable values
  from true zero values and retaining provenance and estimation status. The initial supported set MUST
  be dietary fiber in grams; sodium, potassium, calcium, iron, magnesium, and vitamin C in milligrams;
  and vitamin D and vitamin B12 in micrograms. Each value MUST use a versioned canonical USDA nutrient
  mapping, and an absent or insufficiently covered value MUST remain null rather than become zero.

#### Scope Guardrails

- **FR-031**: The product MUST NOT include an in-app chatbot or open-ended conversational assistant.
- **FR-032**: The product MUST NOT infer nutrition from food photographs.
- **FR-033**: The product MUST NOT require a recurring product subscription for its core self-hosted
  capabilities.
- **FR-034**: The product MUST NOT add social, community, or broad multi-user administration features
  without a separately approved scope change.
- **FR-035**: Nutrition estimates MUST be presented as planning aids rather than medical advice.
  Recipe nutrition, plan-impact, and suggestion preview/acceptance surfaces MUST show concise planning-
  aid language wherever an estimated value can drive a decision. API, MCP, and export documentation
  MUST carry the same limitation; the language MUST remain accessible and MUST NOT obscure provenance,
  uncertainty, or correction controls.
- **FR-036**: Successful-import HTML MUST exist only for the active extraction and be discarded when
  extraction ends. Failed-import HTML MAY be retained only when the owner has enabled diagnostics; it
  MUST be encrypted at rest and deleted within 24 hours. Raw AI/provider requests and responses MUST
  NOT be retained; normalized structured outputs, provenance, input/output hashes, and safe error codes
  MAY be retained. Detailed job diagnostics MUST be deleted or reduced after 30 days to safe codes and
  timestamps retained for no more than one year. Estimates and correction audit history MUST remain
  until explicit owner erasure. Backup documentation MUST disclose that erased records can remain in
  operator-controlled backups until the configured rotation expires. Every permanent recipe deletion
  and owner-erasure operation MUST append a content-free erasure record containing only the erased
  entity type, stable identifier or non-reversible identifier digest, erasure scope, timestamp, and
  monotonic ledger cursor. The ledger MUST be stored independently from restorable application
  backups. Each backup MUST record its ledger cursor, and a staged restore MUST require the current
  ledger, replay every later erasure before validation, and refuse activation when ledger continuity
  cannot be proven. An erasure record MUST remain until all backups predating its erasure have expired
  under configured rotation plus a 30-day safety margin, then MUST be deleted automatically.
  Full owner erasure MUST be available through an offline operator CLI only while application services
  are stopped. It MUST require the owner identifier and exact destructive confirmation, verify that the
  independent ledger can be appended, erase the owner account and all owner-controlled recipes,
  nutrition records, goals, plans, grocery data, suggestions, pantry data, tokens, sessions, jobs,
  outbox records, managed media, diagnostics, and exports, append one `owner`/`owner_owned` ledger
  record, and leave the instance in bootstrap state. It MUST fail closed without partial erasure when
  preconditions or ledger persistence cannot be proven. After the ledger record is durable, any later
  database or managed-file failure MUST keep the instance in maintenance mode and make the command
  idempotently resumable from that record; the instance MUST NOT become active until the entire
  `owner_owned` scope has been applied and verified.
- **FR-037**: Recipe save and import requests that require background work MUST persist the recipe and
  authoritative job and acknowledge within one second rather than wait for nutrition completion.
  Relevant visible screens MUST poll authoritative status every two seconds; other active application
  screens MUST poll every 15 seconds, and reload MUST resume discovery from the stored job. Every
  attempt MUST time out after 60 seconds. Automatic retries MUST wait 5 seconds, 30 seconds, 2 minutes,
  and 5 minutes between successive attempts, stop after at most five attempts, and reach `succeeded`,
  `failed`, `cancelled`, or `superseded` within 15 minutes of initial acceptance. Status responses MUST
  expose progress when measurable, next retry time, and a safe failure code. Terminal failure MUST
  preserve recipe editing and manual nutrition entry and provide an explicit retry action.

### Key Entities

- **Recipe**: A saved dish with title, source, image, yield, instructions, lifecycle state, and ordered
  ingredients; may be created manually or imported.
- **Ingredient**: The original recipe text plus its editable quantity, unit, food identity, optional
  status, and matching or conversion assumptions.
- **Nutrition Estimate**: Recipe- or ingredient-level calories, protein, carbohydrates, fat, optional
  micronutrients, serving basis, source, assumptions, status, and calculation time.
- **Nutrition Correction**: A user-authored replacement for a parsed ingredient, match, conversion,
  serving basis, or nutrient value, including whether it remains active or has been reset.
- **User Goal**: Maintenance energy, target mode, daily calories and macros, optional meal targets,
  tolerances, and effective dates.
- **Meal Plan**: A dated planning period with a week boundary, goal context, and meal entries.
- **Meal Plan Entry**: A recipe snapshot or reference assigned to a date and meal slot with a serving
  quantity and the nutrition basis used for totals.
- **Grocery List**: A plan-derived shopping list with generation state, manual edits, and completion
  state.
- **Grocery Item**: An ingredient quantity or free-form item with normalized identity, unit, source
  recipes, aggregation or pantry deductions, and checked state.
- **Erasure Record**: A content-free, monotonic record of a permanent recipe deletion or owner-erasure
  scope, containing only the identifiers and timing needed to prevent an older backup from restoring
  erased data.
- **Suggestion Request**: A meal, day, or week target, remaining budget, tolerances, exclusions, and
  variety rules supplied by the user.
- **Suggestion Result**: Candidate meal-plan entries, projected totals, satisfied and missed
  constraints, and acceptance state.
- **Pantry Item**: A user-recorded food, quantity, unit, availability, and matching status used for
  search or optional grocery deductions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 90% of a fixed, versioned 50-recipe corpus produce complete per-serving
  calories, protein, carbohydrates, and fat without manual nutrition entry after capture. The corpus
  contains 15 simple, 20 moderate, and 15 complex recipes across multiple cuisines, dietary patterns,
  metric and imperial units, source sites, ambiguous foods, and conversion risks. A result is complete
  only when all four core macros are non-null and ingredient coverage is at least 90%. A stable
  30-recipe primary release subset satisfies the constitution's representative-recipe gate; the other
  20 recipes are extension and stress cases, and the reported product result covers all 50.
- **SC-002**: Against corpus references that publish an unambiguous yield and per-serving calories,
  protein, carbohydrates, and fat, the evaluation has median absolute percentage errors no greater
  than 20% for calories and 25% for each of protein, carbohydrates, and fat, with every discrepancy
  traceable to visible inputs or assumptions. For each nutrient, percentage error is
  `abs(estimate - reference) / reference * 100` and the reported result is the median across every
  eligible corpus recipe. References below 50 kcal, 5 g protein, 5 g carbohydrate, or 2 g fat are
  excluded only from that nutrient's percentage summary and reported separately as median and maximum
  absolute error so near-zero values cannot distort the result. Yield normalization occurs before
  eligibility and error calculation; no unexplained outlier may be removed.
- **SC-003**: All 50 entries in the versioned corpus MUST be captured public recipe pages, and at least
  90% MUST import title, yield, ingredients, and instructions without manual transcription. The result
  MUST also be reported for the stable 30-recipe primary subset and by source site. Stored HTML
  snapshots and expected fields make the result reproducible when a live page changes. These approved,
  non-user benchmark fixtures are test assets and are not retained runtime successful-import HTML.
- **SC-004**: In validation fixtures, 100% of active manual corrections survive reprocessing and are
  used consistently in displayed nutrition, plan totals, suggestions, and external reads.
- **SC-005**: For a seven-day plan containing up to 50 entries, users see updated meal, daily, and
  weekly totals within two seconds of changing an entry or serving count.
- **SC-006**: In calculation fixtures, 100% of meal, day, and week calorie and macro totals and target
  differences exactly match the sum of their displayed serving-level values after round-half-up
  quantization to 1 kcal and 0.1 g. The same fixtures MUST produce identical decimal strings through
  the visual application, HTTP API, MCP tools, exports, and background-job results.
- **SC-007**: In grocery fixtures, 100% of safely compatible repeated ingredients are aggregated to the
  expected quantity and 100% of incompatible or ambiguous quantities remain separate.
- **SC-008**: In a study of at least 20 eligible participants who have never used the product, at least
  90% can import or create a recipe, review its nutrition status, add it to a day, and identify the
  target impact in under five minutes without assistance. The sample MUST include at least five novice
  gym-focused meal planners, five experienced gym-focused meal planners, eight participants completing
  the journey at the narrow-mobile acceptance viewport, and eight completing it on desktop; categories
  MAY overlap. A participant passes only by completing every step within five minutes without hints.
  For samples larger than 20, the required pass count is `ceiling(0.90 * eligible participants)`;
  exclusions and anonymized timing evidence MUST be reported before calculating the rate.
- **SC-009**: For feasible suggestion fixtures, at least 90% of generated plans meet all selected
  calorie, macro, exclusion, and repetition tolerances; all infeasible fixtures identify at least one
  blocking constraint rather than claiming success.
- **SC-010**: In consistency tests, 100% of supported external reads and writes produce the same
  validated state and totals visible in the application, including manual-correction precedence.
- **SC-011**: A backup containing every core entity can be restored with 100% of non-erased recipes,
  active corrections, goals, plan entries, and grocery manual state intact. When the current erasure
  ledger contains records newer than the backup cursor, 100% of those erasures are replayed before the
  restored instance can become active, zero erased recipe-owned records are resurrected, and a missing
  or discontinuous ledger prevents activation with a documented recovery error. A replayed
  `owner_owned` record MUST remove 100% of owner-controlled application and managed-file data and leave
  the restored instance in bootstrap state.
- **SC-012**: Across desktop and narrow-mobile acceptance checks, all primary journeys are operable by
  keyboard, have no horizontal page overflow, and communicate status without color as the only cue.
- **SC-013**: Automated retention and redaction fixtures show that 100% of successful-import HTML is
  absent after extraction, diagnostic HTML expires within 24 hours, detailed diagnostics are reduced
  after 30 days, safe codes and timestamps expire within one year, and no stored record or default log
  contains a raw provider request or response.
- **SC-014**: On a Linux x86-64 Docker host limited to 4 vCPU, 8 GiB RAM, and SSD storage, with API,
  worker, PostgreSQL, and Redis on the same host, 100% of background recipe save/import acceptance
  fixtures return
  a persisted recipe and job within one second; job-state integration fixtures enforce the specified
  attempt timeout, retry schedule, five-attempt maximum, and 15-minute terminal deadline; visible UI
  fixtures surface terminal state within one foreground polling interval and resume after reload.
  Performance reports MUST seed the documented dataset, warm each measured path with 10 unmeasured
  requests, and report p50, p95, and maximum latency over at least 100 measured requests in each of
  three runs.
- **SC-015**: With the optional structured provider disabled and with a substitute forced to time out,
  return invalid output, and fail, 100% of manual recipe editing, manual nutrition entry, goal
  management, meal planning, grocery use, backup, and export acceptance fixtures complete without a
  provider call, state corruption, or loss of a stored recipe; affected automated nutrition work ends
  in an explicit partial or failed state with a recovery action.

## Assumptions

- The initial product is self-hosted and serves one primary user or a small household sharing one goal
  context; separate social profiles, permissions, and multi-tenant administration are out of scope.
- Core product scope consists of P1-P3. P4-P6 are ordered expansion scope after the nutrition pipeline
  and core planning loop meet their success criteria.
- A documented structured application interface is part of the core architecture; a specialized
  personal-agent tool adapter can be delivered with P5 without changing the underlying rules.
- Nutrition values are planning estimates for generally healthy adults, not diagnoses, prescriptions,
  or replacements for professional medical advice.
- URL import is limited to publicly accessible recipe pages. Private, paywalled, or blocked pages can
  fall back to manual recipe entry.
- Common metric and imperial quantities are supported. Ambiguous household measures may require a
  visible density or conversion assumption and user correction.
- The local timezone controls plan dates; the first day of the planning week is user-configurable.
- Suggestions choose only from the user's saved, active recipes and do not invent recipes or nutrition
  values. The user selects target tolerances before accepting a result.
- Initial grocery generation does not subtract pantry stock; pantry-aware deductions belong to P6.
- Specific frameworks, storage systems, automation providers, and the fork-versus-fresh decision are
  planning concerns. FR-005 fixes the required reference-dataset families while planning controls their
  implementation and supported release identifiers.
