# Research: A calmer first kitchen

## Decision: Use a small owner-onboarding record, not a new dashboard or a profile form

**Rationale**: First use is a durable owner state with only three outcomes—pending, completed, or dismissed—and an optional first-action hint. A dedicated owner-scoped record avoids coupling one-time guidance to mutable name/timezone preferences and lets the first-run UI be non-blocking. It also keeps the current recipe, plan, and grocery empty states responsible for contextual follow-up.

**Alternatives considered**:

- Add columns to the owner account: rejected because first-run state has a separate lifecycle from account preferences and would create unnecessary preference-version conflicts.
- Add a permanent home/dashboard route: rejected because it would duplicate Recipes and Plan and make an empty app feel like an unfinished dashboard.
- Force a goals questionnaire: rejected because numeric nutrition targets are useful but optional; mandatory personal metrics contradict the product's calm, inclusive first-use promise.

## Decision: Attach one manually chosen photo through the existing image service and media asset model

**Rationale**: The application already accepts JPEG, PNG, and WebP media; decodes and constrains image dimensions with Pillow; normalizes a recipe image to WebP; stores it through `MediaStore`; and exposes it privately through the authenticated media route. A dedicated authenticated photo replace/remove operation can reuse that safety boundary. The browser can preview a selected file locally before the manual recipe is saved; after recipe creation, the chosen image is attached with an optimistic version check. This keeps recipe content and nutrition processing independent from image failure.

**Alternatives considered**:

- Embed a base64 image in recipe JSON: rejected because it bypasses existing media limits, storage, export, and erasure handling.
- Add a second media system or third-party host: rejected because the current self-hosted media volume already provides owner-controlled storage and export support.
- Send every photo to AI or derive nutrition from it: rejected by the constitution and because a photo cannot supply reliable nutrition provenance.
- Allow a photo gallery or per-step photos: rejected for this slice; one representative image solves visual recognition without building an asset manager.

## Decision: Model favorites, collections, and fixed meal roles as distinct light-weight organizers

**Rationale**: Mealie demonstrates the utility of categories, tags, and cookbooks but also the administration cost of several overlapping taxonomies. Cookfully needs only an immediate favorite marker, optional named many-to-many collections, and the four meal roles already meaningful to its planner. Collections remain a deliberate owner-created grouping; meal roles remain a constrained retrieval aid and never alter planned meal slots.

**Alternatives considered**:

- Free-form tags, cuisine, dietary, occasion, equipment, and saved-search taxonomies: rejected because they create empty management work and a wall of filters before there is user evidence for a specific retrieval need.
- A single cookbook/tag abstraction: rejected because it cannot distinguish a trusted favorite from a project collection or an ordinary meal role without overloaded semantics.
- One collection per recipe: rejected because a personal recipe can sensibly be both a freezer-friendly batch and a weeknight dinner.

## Decision: Add owner-named shopping stops, opt-in remembered placements, and an explicit completed list state

**Rationale**: Tandoor and Mealie validate meal-plan-derived shopping and item ordering/labels, but their broad configuration is not appropriate as a default. A small ordered list of personal shopping stops (for example, produce market and supermarket) provides real-world routing. A preference is applied only to safe generated items with a stable normalized food identity; manually renamed or ambiguous items remain unassigned. A completed state preserves the actual weekly purchase record instead of treating a fully checked list as disposable.

**Alternatives considered**:

- One mutable free-text label on every item: rejected because it does not provide a reusable ordering model or safe remembered placement.
- Retailer catalogue, product prices, checkout, or delivery integrations: rejected because they add regional providers, secrets, and operational complexity without improving the core list reliably.
- Silently regenerate a completed list after a plan changes: rejected because it would alter a historical shopping record. Reopening is an explicit owner action.
- Automatic placement based on an AI classifier: rejected because store preference is personal and deterministic owner choices are safer and clearer.

## Decision: Keep media upload synchronous but bounded; do not add a new background job

**Rationale**: Existing image processing is constrained to a single local file, has a fixed size and dimension ceiling, and performs a finite decode/normalization operation. It does not call an external provider or touch nutrition. The request will show a pending state and safe error recovery. Nutrition and import jobs remain asynchronous and idempotent exactly as they are today.

**Alternatives considered**:

- Route every image through the task queue: rejected because it would make a single optional photo feel unreliable and add job-management complexity without a remote or expensive transformation.
- Trust only the browser-provided MIME type: rejected because the existing Pillow decode is the needed server-side content validation step.

## Decision: Keep ordinary kitchen navigation stable and place organization contextually

**Rationale**: The existing Recipes, Plan, Grocery, Pantry, and secondary navigation already establish the primary kitchen sequence. First-run is conditional, collections are accessed from Recipes, and grocery stops are accessed where shopping occurs. This follows the project design rule that one region has one primary action and avoids promoting setup concepts into permanent navigation.

**Alternatives considered**:

- Add global navigation entries for Onboarding, Collections, and Stores: rejected because these are supporting contexts, not daily destinations.
- Put all metadata fields in the manual recipe form: rejected because title, yield, ingredients, and method must remain the first task; image and organization are optional disclosures.
