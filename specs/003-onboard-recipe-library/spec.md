# Feature Specification: A calmer first kitchen

**Feature Branch**: `003-onboard-recipe-library`
**Created**: 2026-08-13
**Status**: Draft
**Input**: User description: "Create a polished first-run journey; let people attach photos to manually created recipes; complete the grocery shopping flow; and add a lightweight recipe organization layer for health-conscious home cooks."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Start with one useful action (Priority: P1)

As a new owner, I want Cookfully to help me choose a small first step rather than present an empty library or a long setup form, so I can begin using it without deciding everything about my health or kitchen at once.

**Why this priority**: A person cannot receive value from planning, organization, or grocery support until they understand the first useful action and can preserve a recipe they want to cook.

**Independent Test**: Start with a newly authenticated owner who has no recipe or completed introduction, choose a first task, complete or dismiss it, and verify that the owner reaches the appropriate real feature without the introduction repeatedly interrupting them.

**Acceptance Scenarios**:

1. **Given** an owner opening Cookfully for the first time, **When** they reach the kitchen, **Then** they see a calm introduction that explains the recipe-to-plan-to-grocery journey and offers clear next actions: write a recipe, import a recipe, or view the week.
2. **Given** a first-time owner, **When** they choose to write or import a recipe, **Then** Cookfully opens the selected creation path directly, with no additional questionnaire required.
3. **Given** a first-time owner, **When** they choose to view the week before adding recipes, **Then** Cookfully explains the next useful action without blocking access to the planner.
4. **Given** an owner who dismisses the introduction or completes one of its paths, **When** they return to Cookfully or use another signed-in device, **Then** the introduction does not reappear as a blocking screen and its guidance remains discoverable from relevant empty states.
5. **Given** an owner who has not created a nutrition guide, **When** they use the first-run journey, **Then** Cookfully may explain that a guide is optional but does not ask for body measurements, impose a diet identity, or prevent recipe and plan use.

---

### User Story 2 - Give a handwritten recipe a home (Priority: P1)

As a home cook writing a recipe from memory, a notebook, or a family message, I want to attach one representative photo while I create it, so the recipe feels recognizable and inviting when I return to it.

**Why this priority**: Food imagery makes a personal library easier to scan and makes manual recipes feel as complete as imported ones, without making photography a prerequisite for saving dinner.

**Independent Test**: Create a recipe with a photo, confirm it is visible in the recipe detail and library, replace it, then remove it; create another recipe without a photo and confirm it remains fully usable with Cookfully fallback art.

**Acceptance Scenarios**:

1. **Given** an owner creating a recipe manually, **When** they choose a supported photo or capture one from a capable mobile device, **Then** they see a preview and can remove or replace it before saving.
2. **Given** a manually created recipe with a saved photo, **When** the owner opens its detail, planning picker, or library card, **Then** Cookfully uses that photo where recipe imagery is shown.
3. **Given** an owner editing a manually created recipe, **When** they replace or remove its photo, **Then** the new image or fallback presentation appears without changing ingredients, instructions, servings, source, or nutrition.
4. **Given** a photo upload that cannot be accepted, **When** Cookfully reports the problem, **Then** it keeps the existing saved photo (if any), explains what the owner can do next, and still allows the recipe to be saved without a photo.
5. **Given** an imported recipe with source imagery, **When** this feature is released, **Then** its existing image continues to work and is not silently replaced by a manual-recipe photo workflow.

---

### User Story 3 - Shop by the way I actually shop (Priority: P2)

As a meal planner at the store, I want one uncluttered list grouped by my shopping stops, with a clear finish to the trip, so I can reliably turn this week's plan into food at home.

**Why this priority**: The grocery list is the handoff from an intentional plan to real meals. A flat list with no sense of progress or store order leaves the journey half finished.

**Independent Test**: Generate a weekly list with plan-derived and manual items, add two shopping stops, assign items, refresh after a plan change, check off every item, and finish the shop without losing item provenance or the next week's planning ability.

**Acceptance Scenarios**:

1. **Given** a generated or manually extended grocery list, **When** the owner creates one or more named shopping stops and assigns items, **Then** the list groups items by stop and keeps unassigned items visible in a clear fallback group.
2. **Given** an owner who assigns a grocery item to a stop and chooses to remember that choice, **When** the same ingredient appears in a later generated list, **Then** Cookfully applies the remembered owner-specific placement while still allowing an immediate correction.
3. **Given** a shopping stop is renamed, reordered, or deleted, **When** the owner returns to the current list, **Then** labels and grouping update predictably; deleting a stop moves its items and remembered placements to the unassigned group rather than removing grocery items.
4. **Given** a plan change makes a grocery list stale, **When** the owner refreshes the list, **Then** Cookfully retains completed items, manual items, owner-selected stops, and source visibility while updating plan-derived quantities and clearly identifying anything that needs review.
5. **Given** all current grocery items are checked off, **When** the owner finishes the shop, **Then** the list becomes a completed record for that week, shows a calm completion state, and does not prevent planning or generating a later weekly list.
6. **Given** items remain unchecked, **When** the owner tries to finish the shop, **Then** Cookfully names how many items remain and keeps the list active instead of silently discarding them.

---

### User Story 4 - Keep familiar recipes easy to find (Priority: P2)

As someone building a personal recipe collection, I want lightweight ways to save favorites, keep recipes in a few named collections, and indicate when I usually cook them, so I can find the right meal without turning recipe entry into metadata work.

**Why this priority**: A growing private library becomes less useful if healthy, trusted meals are indistinguishable from one-off imports. Organization should improve recall without recreating a power-user administration screen.

**Independent Test**: Mark recipes as favorites, create and rename collections, add a recipe to more than one collection, assign meal roles, filter the library by each organizer, and verify recipes with no organizer remain searchable and usable.

**Acceptance Scenarios**:

1. **Given** any active recipe, **When** the owner marks or unmarks it as a favorite, **Then** the change is immediately visible from its detail and the library's favorites view.
2. **Given** an owner organizing a recipe, **When** they create a named collection or add the recipe to an existing one, **Then** that recipe may belong to more than one collection and the owner can later remove it without deleting the recipe or collection.
3. **Given** an owner organizing a recipe, **When** they select one or more standard meal roles (breakfast, lunch, dinner, or snack), **Then** those roles are available as an optional library filter and never change the recipe's nutrition, planned meal slot, or cooking instructions.
4. **Given** a recipe has no favorite, collection, or meal role, **When** the owner saves or plans it, **Then** Cookfully does not require organization metadata and the recipe remains discoverable through ordinary search and planning.
5. **Given** the owner opens the recipe library on desktop or mobile, **When** they use favorites, one collection, or a meal-role filter, **Then** the resulting recipes remain searchable, have a clear way to remove the filter, and do not require a wall of simultaneous filter controls.
6. **Given** a collection is renamed or deleted, **When** the owner views the library, **Then** affected recipes remain intact; deleting a collection only removes that membership.

### Edge Cases

- What happens when an owner first opens Cookfully while offline or the introduction state cannot be saved? The owner must still reach Recipes, Plan, and existing content, with a retryable non-blocking message rather than a locked first-run screen.
- What happens when a selected photo is an unsupported type, exceeds the documented size limit, is corrupt, or the connection fails? The owner receives a specific recovery action, no partial image replaces an existing one, and the recipe can remain photo-free.
- What happens when two browser sessions change the same recipe organization, shopping-stop list, or grocery item? Cookfully shows the current-data conflict and lets the owner reload before retrying; it never silently overwrites a newer change.
- What happens when a remembered grocery placement matches an ambiguous or manually renamed item? Cookfully leaves the item unassigned and makes the owner choose rather than applying an unreliable store assignment.
- What happens when a completed list is regenerated for the same week? Cookfully requires an explicit choice to reopen or start a new active shopping pass and never erases the completed record invisibly.
- What happens at 200% zoom, on a 390x844 phone, or with long recipe titles and store names? Controls and labels must reflow without document-level horizontal scrolling or inaccessible actions.

## Constitution Alignment *(mandatory)*

- **Macro-goal contribution**: This feature lowers the friction between saving familiar food, planning it, buying it, and cooking it. Nutrition remains useful planning evidence, not an intake-tracking demand or a condition of first use.
- **Nutrition and estimation impact**: Photos, favorites, collections, meal roles, and grocery-stop organization do not create, infer, hide, or alter nutrition values. Recipe photos and organization cannot overwrite ingredient provenance, serving basis, active corrections, plan snapshots, or the visible estimated/partial/manual nutrition state.
- **Structured processing**: No AI inference or automatic food/nutrition matching is introduced. Photo acceptance and persistence must have explicit pending, successful, and failed states; retrying a failed upload must not duplicate a photo or overwrite a newer one.
- **Data and agent access**: All new data is owner-scoped. Recipe photos, organization, grocery stops, remembered placements, and completed shopping state are included in documented owner export and full-owner erasure. Any structured API or agent read/write exposure must keep the same owner boundaries, explicit mutation confirmation, version-conflict behavior, and provider-independent usability as the visual workflow.
- **Reuse and experience**: Adapt Mealie/Tandoor's useful link between personal collections, meal planning, and shopping, but reject their broad tag/configuration surfaces. Adapt Immich's direct, status-visible media handling without treating a recipe photo as a gallery asset. Follow `DESIGN.md`: food leads imagery; only one primary action per region; organization is progressive disclosure; every surface has loading, empty, partial, stale, failed, and unavailable states; keyboard navigation, meaningful image alternatives, and 1440x900 plus 390x844 verification are required.
- **Explicit non-goals**: This feature does not add social sharing, multi-owner collaboration, household management, arbitrary free-form tags, cuisine/dietary/occasion taxonomies, automatic AI labels, meal-consumption tracking, product pricing, retailer checkout, delivery integration, automatic pantry depletion, multiple recipe photos, per-step photos, or medical/nutrition advice.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST show a first-run journey only to an authenticated owner who has neither completed nor dismissed it, and it MUST offer direct routes to manual recipe creation, recipe import, and the weekly planner.
- **FR-002**: The first-run journey MUST explain in plain language that nutrition guidance is optional and MUST NOT require health metrics, diet labels, recipe metadata, or a nutrition guide before the owner can use the recipe library or planner.
- **FR-003**: The system MUST persist an owner's completion or dismissal of the first-run journey across signed-in sessions and devices.
- **FR-004**: Relevant empty states in Recipes, Plan, and Grocery MUST continue to present a next useful action after the first-run journey has been completed or dismissed.
- **FR-005**: The system MUST let an owner attach, preview, replace, and remove one optional representative photo while creating or editing a manually created recipe.
- **FR-006**: The system MUST accept only documented common raster image formats and a documented maximum file size, reject unsupported or invalid files before replacing a saved photo, and give the owner an actionable error message.
- **FR-007**: The system MUST present a saved recipe photo consistently in its recipe detail, library, planning picker, suggestion result, and Cook Mode wherever recipe media is already supported; recipes without a photo MUST use the existing non-deceptive fallback art.
- **FR-008**: The system MUST preserve all recipe content and nutrition data when a photo is added, replaced, removed, or fails to save.
- **FR-009**: The system MUST let an owner create, rename, reorder, and delete named grocery shopping stops for their own use.
- **FR-010**: The system MUST let an owner assign each current grocery item to one shopping stop or leave it unassigned, and MUST group the active list accordingly with an always-visible unassigned fallback group.
- **FR-011**: The system MUST let an owner opt to remember a placement for a clearly matched grocery item and MUST apply that owner-specific preference to matching future generated items; the owner MUST be able to correct or remove remembered placements.
- **FR-012**: Grocery regeneration MUST preserve manual items, checked state, owner-selected shopping-stop assignments, source provenance, and safe pantry deductions exactly as current contracts require; it MUST clearly surface changes that cannot be reconciled.
- **FR-013**: The system MUST show active-list progress as the number of items remaining and MUST allow an owner to finish a shopping pass only when no items remain unchecked.
- **FR-014**: The system MUST retain a finished shopping pass with its week, items, completion time, and source provenance; it MUST require an explicit owner choice before reopening or replacing a completed pass for the same week.
- **FR-015**: The system MUST let an owner mark any active recipe as a favorite without requiring a collection or meal role.
- **FR-016**: The system MUST let an owner create, rename, and delete named recipe collections, add a recipe to zero or more collections, and remove a collection membership without changing recipe content, planning history, or nutrition.
- **FR-017**: The system MUST offer only the four standard optional meal roles—breakfast, lunch, dinner, and snack—and let an owner assign zero or more roles to a recipe.
- **FR-018**: The recipe library MUST offer focused, removable ways to view favorites, one collection, or one meal role alongside ordinary search and existing readiness/archive views; it MUST not require owners to fill in or manage arbitrary tags to find recipes.
- **FR-019**: Recipe organization controls MUST be optional and progressively disclosed from recipe detail and library contexts; manual recipe entry MUST remain focused on title, yield, ingredients, and method.
- **FR-020**: The system MUST include the new owner-scoped photo, first-run, organization, grocery-stop, remembered-placement, and shopping-completion data in owner export and full-owner erasure behavior.
- **FR-021**: Each changed screen MUST provide explicit loading, empty, partial, stale, failed, and conflict recovery states appropriate to its data, including a non-destructive retry path for failed photo processing and grocery updates.
- **FR-022**: All new interactions MUST be keyboard operable, announce meaningful status or error changes, maintain visible focus, use useful text alternatives for saved recipe photos, and work without document-level horizontal overflow at 390x844 and 1440x900.

### Key Entities *(include if feature involves data)*

- **First-run journey state**: An owner-scoped record of whether the introductory journey is pending, completed, or dismissed, plus the most recently chosen first action when useful for resuming context.
- **Recipe photo**: One owner-controlled representative image attached to a manually created recipe, including its lifecycle state and display-safe metadata; it is optional and independent of recipe nutrition.
- **Recipe collection**: An owner-named grouping that can contain many recipes; a recipe can belong to many collections, and deleting a collection only removes memberships.
- **Recipe meal role**: One of the standard optional planning-oriented labels assigned to a recipe: breakfast, lunch, dinner, or snack.
- **Grocery shopping stop**: An owner-named, ordered shopping destination used to group items in an active grocery list.
- **Remembered grocery placement**: An owner-scoped preference that associates a reliably identified grocery item with a shopping stop for later generated lists.
- **Shopping pass**: The active or completed grocery-list experience for a particular week, including item completion, optional finish time, manual edits, and plan-derived provenance.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In moderated first-use testing, at least 90% of new owners reach either the manual recipe form, recipe import, or weekly plan within 60 seconds without assistance.
- **SC-002**: In usability testing, at least 90% of owners can create and save a basic manual recipe—with or without a photo—in under 3 minutes, and no task failure is caused by declining to add an image.
- **SC-003**: At least 95% of valid recipe-photo selections show a usable preview within 10 seconds on a normal broadband or modern mobile connection; failed selections retain the prior recipe state in 100% of acceptance tests.
- **SC-004**: In a 15-item weekly-list scenario across two shopping stops, at least 90% of owners can group, check off, and finish the list in under 2 minutes without assistance.
- **SC-005**: In acceptance fixtures, 100% of regenerated grocery lists preserve completed/manual items and their required provenance, and 100% of deleted shopping stops retain their grocery items in the unassigned group.
- **SC-006**: In a 25-recipe library scenario, at least 90% of owners can find a favorited recipe, a recipe in a named collection, and a dinner recipe within two deliberate interactions after opening the library.
- **SC-007**: All changed first-run, recipe, grocery, and library workflows complete by keyboard and at 390x844 and 1440x900 without document-level horizontal overflow, with explicit loading, empty, partial, stale, conflict, and failure evidence.

## Assumptions

- Cookfully remains a single-owner, self-hosted product for this feature; sharing, collaboration, and delegated organization are deliberately deferred.
- The existing manual recipe and URL-import paths remain the two recipe-entry paths; photo/PDF recipe extraction is not part of this feature.
- One representative image is sufficient for a first release. Owners may skip it, and existing imported images continue to be governed by their current source behavior.
- Shopping stops are personal routing aids, not retailer catalogs, price comparisons, delivery integrations, or product substitutions.
- Existing grocery quantity aggregation, source provenance, pantry safeguards, optimistic concurrency, recipe archive behavior, nutrition snapshots, owner export, and erasure guarantees remain authoritative.
- Existing Recipes, Plan, Grocery, Pantry, Foods, Goals, and Settings navigation remains recognizable; first-run guidance improves entry without adding a permanent dashboard destination.
