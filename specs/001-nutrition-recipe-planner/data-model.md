# Phase 1 Data Model: Gym-Focused Recipe & Nutrition Planner

**Date**: 2026-08-09  
**Database target**: PostgreSQL 18

## Modeling Conventions

- Primary identifiers are UUIDv7 values. Public contracts expose them as strings.
- Timestamps are stored as timezone-aware UTC instants; user-local dates and week boundaries are
  stored separately where calendar meaning matters.
- Nutrition and quantity values use fixed-precision decimals. Database constraints reject NaN,
  infinity, and negative values unless a field explicitly represents a signed difference.
- Every mutable aggregate has an integer `version` used for optimistic concurrency.
- Core nutrition facts, statuses, serving bases, and relationships use typed columns. JSON is limited
  to raw provider payloads, non-authoritative source metadata, and audit details.
- `created_at`, `updated_at`, and actor/origin metadata are present on mutable records. Secrets and raw
  provider prompts are never audit fields.
- Archive is preferred over hard deletion for recipes used by plans. Hard deletion is limited to
  unreferenced drafts or explicit data-erasure workflows.

## Core Identity and Access

### OwnerAccount

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `email` | case-insensitive text | Unique, normalized, required |
| `display_name` | text | 1-80 characters |
| `password_hash` | text | Argon2id hash only |
| `timezone` | IANA zone | Required |
| `week_starts_on` | small integer | 1-7, ISO weekday |
| `status` | enum | `active`, `locked`, `disabled` |
| `version` | integer | Optimistic concurrency |

Initial scope creates one owner. The model does not add households, roles, invitations, feeds, or
social profiles.

### Session

| Field | Type | Rules |
|---|---|---|
| `id_hash` | bytes/text | Primary key; raw token never stored |
| `owner_id` | UUID | FK to OwnerAccount |
| `csrf_secret_hash` | bytes/text | Required |
| `created_at`, `expires_at`, `last_seen_at` | timestamp | Expiry after creation |
| `revoked_at` | timestamp nullable | Revoked sessions are unusable |
| `client_label` | text nullable | User-visible session identification |

### AccessToken

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `owner_id` | UUID | FK to OwnerAccount |
| `token_hash` | bytes/text | Unique; raw token shown once |
| `name` | text | Required, user-visible |
| `scopes` | text array | Subset of `recipes:read`, `goals:read`, `plans:read`, `plans:write`, `grocery:read`, `grocery:write` |
| `expires_at`, `last_used_at`, `revoked_at` | timestamp nullable | Revocation wins over expiry |

## Recipe Aggregate

### Recipe

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `title` | text | 1-240 characters |
| `description` | text nullable | Plain text/limited safe markup |
| `source_url` | URL nullable | HTTP/HTTPS only; final canonical URL retained separately |
| `source_name` | text nullable | Human-readable attribution |
| `yield_quantity` | decimal | Greater than zero when known |
| `yield_unit` | text | Default `servings`; controlled vocabulary plus custom display text |
| `prep_minutes`, `cook_minutes` | integer nullable | Non-negative |
| `status` | enum | `draft`, `processing`, `ready`, `partial`, `failed`, `archived` |
| `nutrition_state` | enum | `pending`, `source_provided`, `estimated`, `partial`, `failed`, `stale` |
| `active_estimate_id` | UUID nullable | FK to NutritionEstimate; set only after successful validation |
| `image_asset_id` | UUID nullable | FK to MediaAsset |
| `input_hash` | text | Hash of nutrition-relevant recipe inputs |
| `archived_at` | timestamp nullable | Required only for `archived` |
| `version` | integer | Optimistic concurrency |

Relationships: one Recipe has ordered RecipeInstructions and Ingredients, many NutritionEstimates and
NutritionCorrections, optional MediaAssets, and may be referenced by MealPlanEntries.

### RecipeInstruction

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `recipe_id` | UUID | FK to Recipe, cascade with unreferenced recipe deletion |
| `position` | integer | Zero-based, unique within recipe |
| `text` | text | Required |

### Ingredient

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `recipe_id` | UUID | FK to Recipe |
| `position` | integer | Zero-based, unique within recipe |
| `original_text` | text | Immutable capture of the displayed/imported line |
| `quantity_min`, `quantity_max` | decimal nullable | Non-negative; max >= min |
| `unit_code` | text nullable | Canonical unit when resolved |
| `unit_text` | text nullable | Original/custom unit display |
| `food_name` | text nullable | Editable normalized name |
| `preparation` | text nullable | e.g. diced, drained |
| `comment` | text nullable | Non-quantity qualifier |
| `purpose` | text nullable | e.g. garnish |
| `optional` | boolean | Default false |
| `parse_status` | enum | `unparsed`, `parsed`, `low_confidence`, `manual`, `failed` |
| `parse_confidence` | decimal nullable | 0 through 1; not presented as nutrition accuracy |
| `parser_name`, `parser_version` | text nullable | Provenance |
| `version` | integer | Optimistic concurrency |

Editing a structured field does not mutate `original_text`; it creates or updates a correction record
and changes the recipe input hash.

### MediaAsset

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `recipe_id` | UUID nullable | FK to Recipe |
| `kind` | enum | `recipe_image`, `export_archive` |
| `storage_key` | text | Relative key only; unique |
| `content_type` | text | Allowlisted |
| `byte_size` | bigint | Positive and within configured limit |
| `sha256` | text | Integrity and deduplication |
| `source_url` | URL nullable | Attribution only; never used as a filesystem path |

## Reference Nutrition and Matching

### ReferenceDataset

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `provider` | enum | Initially `usda_fdc` |
| `dataset_type` | text | e.g. `foundation`, `sr_legacy`, `branded` |
| `release_id` | text | Unique with provider and type |
| `released_on`, `imported_at` | date/timestamp | Required |
| `source_url` | URL | Required |
| `license` | text | Required, e.g. `CC0-1.0` |
| `active` | boolean | Only one active release per provider/type |

### FoodReference

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `dataset_id` | UUID | FK to ReferenceDataset |
| `external_id` | text | Unique within dataset |
| `description` | text | Required |
| `normalized_name` | text | Search-indexed |
| `data_type` | text | Foundation, SR Legacy, branded, etc. |
| `brand_owner` | text nullable | Branded records only |
| `food_category` | text nullable | Search/ranking hint |
| `basis_grams` | decimal | Normally 100, greater than zero |

### FoodNutrient

| Field | Type | Rules |
|---|---|---|
| `food_reference_id` | UUID | Composite PK/FK |
| `nutrient_code` | text | Composite PK; canonical internal code |
| `amount` | decimal nullable | Null means unavailable; zero is a measured/declared zero |
| `unit` | enum | `kcal`, `g`, `mg`, `ug`, etc. |
| `derivation` | text nullable | Provider derivation/provenance |

### IngredientMatch

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `ingredient_id` | UUID | FK to Ingredient |
| `food_reference_id` | UUID nullable | FK to FoodReference; nullable if unmatched |
| `status` | enum | `candidate`, `matched`, `ambiguous`, `unmatched`, `manual` |
| `match_method` | enum | `exact`, `alias`, `ranked`, `ai_disambiguated`, `manual` |
| `match_score` | decimal nullable | 0 through 1, internal ranking only |
| `grams_min`, `grams_max` | decimal nullable | Non-negative |
| `conversion_method` | enum nullable | `mass`, `count_weight`, `density`, `manual` |
| `density_g_per_ml` | decimal nullable | Positive; source required when set |
| `assumption_text` | text nullable | User-visible explanation |
| `source_release_id` | text nullable | Frozen reference release |
| `input_hash` | text | Unique with active match attempt |
| `active` | boolean | At most one active match per ingredient |

## Nutrition Results and Corrections

### NutritionEstimate

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `recipe_id` | UUID | FK to Recipe |
| `status` | enum | `source_provided`, `estimated`, `partial`, `failed`, `superseded` |
| `basis_servings` | decimal | Greater than zero |
| `calories_kcal`, `protein_g`, `carbohydrate_g`, `fat_g` | decimal nullable | Per serving; non-negative |
| `fiber_g`, `sodium_mg`, other typed expansion nutrients | decimal nullable | Null means unavailable |
| `coverage_ratio` | decimal | 0 through 1 by ingredient mass/known contribution |
| `source_label`, `source_url` | text/URL nullable | Required for source-provided data |
| `assumptions_summary` | text nullable | User-visible |
| `input_hash` | text | Recipe inputs used |
| `pipeline_version` | text | Required |
| `calculated_at` | timestamp | Required |
| `supersedes_id` | UUID nullable | Self-FK |

An estimate is immutable after activation. Reprocessing creates a new record and atomically changes
`Recipe.active_estimate_id` only if the recipe input hash is still current.

### NutritionCorrection

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `recipe_id` | UUID | FK to Recipe |
| `ingredient_id` | UUID nullable | Set for ingredient-scoped corrections |
| `field` | enum | Explicit allowlist: parsed quantity/unit/name, match, grams, yield, or nutrient field |
| `decimal_value` | decimal nullable | Used for numeric corrections |
| `text_value` | text nullable | Used for name/unit/reasoned corrections |
| `reference_id_value` | UUID nullable | Used for reference-food correction |
| `reason` | text nullable | User note |
| `active` | boolean | At most one active correction per scope+field |
| `created_by` | UUID | OwnerAccount |
| `reset_at` | timestamp nullable | Reset retains audit history |

Exactly one typed value column is populated according to `field`. Active corrections are applied after
automatic results and before every rollup, snapshot, suggestion, export, API read, or MCP read.

## Durable Processing

### ProcessingJob

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key and external job ID |
| `kind` | enum | `recipe_import`, `ingredient_parse`, `nutrition_match`, `nutrition_rollup`, `export`, `restore`, later `suggestion` |
| `aggregate_type`, `aggregate_id` | text/UUID | Target identity |
| `input_hash` | text | Idempotency and stale-write guard |
| `status` | enum | `queued`, `running`, `retry_wait`, `succeeded`, `failed`, `cancelled`, `superseded` |
| `attempt`, `max_attempts` | integer | 0 <= attempt <= max |
| `progress_current`, `progress_total` | integer nullable | Non-negative |
| `failure_code`, `failure_message` | text nullable | Safe/user-presentable; no secrets |
| `available_at`, `started_at`, `heartbeat_at`, `finished_at` | timestamp nullable | State-dependent |
| `celery_task_id` | text nullable | Diagnostic only; not source of truth |

Unique active-job constraint: one nonterminal job per `(kind, aggregate_id, input_hash)`.

### OutboxEvent

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `event_type` | text | Versioned, allowlisted |
| `aggregate_id` | UUID | Usually ProcessingJob ID |
| `payload_version` | integer | Required |
| `payload` | JSON | IDs, input hash, and tracing only; no recipe body/secrets |
| `created_at`, `published_at` | timestamp | Published nullable |
| `publish_attempts` | integer | Non-negative |

## Goals and Meal Planning

### UserGoal

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `owner_id` | UUID | FK to OwnerAccount |
| `mode` | enum | `cut`, `maintain`, `bulk` |
| `maintenance_kcal`, `target_kcal` | decimal | Greater than zero |
| `protein_g`, `carbohydrate_g`, `fat_g` | decimal | Non-negative; at least one macro positive |
| `effective_from`, `effective_to` | local date | Non-overlapping; end nullable |
| `notes` | text nullable | User-visible |
| `version` | integer | Optimistic concurrency |

The application displays the difference between macro-derived calories and `target_kcal` when outside
a defined rounding tolerance; it does not silently rewrite user targets.

### MealTarget

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `user_goal_id` | UUID | FK to UserGoal |
| `meal_slot` | enum/text | Unique within goal; defaults breakfast/lunch/dinner/snack |
| `calories_kcal`, `protein_g`, `carbohydrate_g`, `fat_g` | decimal nullable | Non-negative; null inherits no per-meal target |
| `position` | integer | Unique within goal |

### MealPlan

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `owner_id` | UUID | FK to OwnerAccount |
| `week_start` | local date | Unique per owner and chosen week convention |
| `timezone` | IANA zone | Frozen for calendar interpretation |
| `goal_id` | UUID | FK to UserGoal effective for plan |
| `version` | integer | Optimistic concurrency |

### MealPlanEntry

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `meal_plan_id` | UUID | FK to MealPlan |
| `local_date` | date | Within the plan's seven-day interval |
| `meal_slot` | text | Required |
| `position` | integer | Unique per date+slot |
| `recipe_id` | UUID nullable | FK retained while recipe exists/archived |
| `recipe_title_snapshot` | text | Required |
| `servings` | decimal | Greater than zero, bounded by configured maximum |
| `nutrition_snapshot_id` | UUID | FK to MealNutritionSnapshot |
| `origin` | enum | `manual`, `suggestion`, `external` |
| `version` | integer | Optimistic concurrency |

### MealNutritionSnapshot

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `recipe_id`, `estimate_id` | UUID nullable | Provenance links |
| `basis_servings` | decimal | Serving multiplier represented |
| `calories_kcal`, `protein_g`, `carbohydrate_g`, `fat_g` | decimal nullable | Resolved values after corrections |
| `nutrition_state` | enum | `source_provided`, `estimated`, `partial`, `manual` |
| `coverage_ratio` | decimal | 0 through 1 |
| `captured_at` | timestamp | Immutable |

Plan totals are sums of snapshot values, never live joins to mutable recipe estimates. A user may
explicitly refresh selected entries to a newer estimate, creating replacement snapshots.

## Grocery Aggregate

### GroceryList

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `meal_plan_id` | UUID | Unique FK to MealPlan |
| `status` | enum | `current`, `dirty`, `generating`, `failed` |
| `source_plan_version` | integer | Plan version used for generation |
| `generated_at` | timestamp nullable | Required when current |
| `version` | integer | Optimistic concurrency |

### GroceryItem

| Field | Type | Rules |
|---|---|---|
| `id` | UUIDv7 | Primary key |
| `grocery_list_id` | UUID | FK to GroceryList |
| `normalized_food_name`, `display_name` | text | Required |
| `quantity` | decimal nullable | Non-negative |
| `unit_code`, `unit_text` | text nullable | Canonical and display forms |
| `aggregation_key` | text nullable | Only set for safely equivalent items |
| `origin` | enum | `generated`, `manual` |
| `checked` | boolean | Default false |
| `manual_quantity`, `manual_name` | boolean | Protect edits during regeneration |
| `needs_review` | boolean | True for affected ambiguous reconciliation |
| `position` | integer | Stable user ordering |
| `version` | integer | Optimistic concurrency |

### GroceryItemSource

| Field | Type | Rules |
|---|---|---|
| `grocery_item_id` | UUID | Composite PK/FK |
| `meal_plan_entry_id` | UUID | Composite PK/FK |
| `ingredient_id` | UUID nullable | Provenance when recipe remains available |
| `quantity_contribution` | decimal nullable | In GroceryItem unit when convertible |
| `original_text` | text | Required traceability |

Regeneration computes proposed generated items, reconciles them by stable source and aggregation key,
and preserves checked/manual fields. Removed or materially changed sources mark affected items for
review rather than silently deleting manual state.

## Expansion Entities

### SuggestionRun and SuggestionItem (P4)

`SuggestionRun` stores scope (`meal`, `day`, `week`), target snapshot, tolerances, exclusions,
required recipes, repetition limit, solver/pipeline version, time limit, status (`queued`, `running`,
`feasible`, `infeasible`, `failed`, `expired`), objective score, and unmet constraints.
`SuggestionItem` stores the candidate recipe, date/slot, servings, projected nutrition snapshot, and
acceptance state. Accepted items go through the normal MealPlan command and concurrency checks.

### PantryItem and PantryDeduction (P6)

`PantryItem` stores normalized/display food identity, quantity/unit, optional FoodReference, match
status, and version. `PantryDeduction` links a GroceryItem to a PantryItem with the converted amount,
assumption, and reversible state. No ambiguous match is deducted automatically.

## State Transitions

```text
Recipe:
draft -> processing -> ready
                  \-> partial
                  \-> failed
ready|partial|failed -> processing        (explicit retry/recalculate)
any non-archived -> archived -> prior usable state

ProcessingJob:
queued -> running -> succeeded
                  \-> retry_wait -> queued
                  \-> failed
queued|retry_wait -> cancelled
queued|running|retry_wait -> superseded   (input hash changed)

GroceryList:
current -> dirty -> generating -> current
                            \-> failed -> dirty

SuggestionRun:
queued -> running -> feasible
                  \-> infeasible
                  \-> failed
feasible|infeasible -> expired
```

Invalid transitions return a conflict response and do not mutate the aggregate.

## Calculation and Precedence Rules

1. Resolve source-provided or ingredient-derived estimate for the current recipe input hash.
2. Apply active ingredient corrections before reference matching and gram conversion.
3. Apply active nutrient/yield corrections after rollup.
4. Divide full-recipe nutrients by the corrected positive serving yield.
5. Store per-serving values at higher internal precision; round only at display/contract boundaries.
6. Snapshot resolved values when a meal entry is created or explicitly refreshed.
7. Sum snapshots for meal/day/week totals. Propagate the least reliable contributing status and
   minimum coverage ratio alongside the numeric total.
8. Generate grocery contributions from ingredient quantities and planned servings, not nutrition
   snapshots. Combine only matching food identity and dimensionally convertible units.

## Required Indexes and Constraints

- Unique normalized owner email and token hash.
- Recipe title search plus trigram indexes on Recipe title, Ingredient food name, and FoodReference
  normalized name.
- Unique ordered positions inside recipe instructions, ingredients, meal slots, and grocery lists.
- Partial unique indexes for active IngredientMatch and active NutritionCorrection scope+field.
- Job index on `(status, available_at)` and uniqueness for active kind+aggregate+input hash.
- Outbox index on unpublished creation order.
- UserGoal exclusion constraint preventing overlapping effective date ranges.
- Unique MealPlan owner+week start and GroceryList meal plan.
- MealPlanEntry indexes on plan+date+slot and Recipe references.
- Check constraints for positive servings/yields, non-negative nutrient values, valid confidence/
  coverage range, and state-dependent timestamps.

## Retention and Deletion

- Archiving a recipe removes it from normal search/suggestions but keeps historical plan links.
- Hard deletion of a referenced recipe first detaches the nullable reference; title and nutrition
  snapshots remain. Grocery source text remains.
- Raw fetched HTML is retained only in test fixtures or short-lived diagnostic storage with an
  explicit expiry; it is not permanent recipe data.
- Provider response payloads are minimized and may be purged after normalized provenance is stored.
- Job failure details are retained long enough for diagnosis, then reduced to safe failure code and
  timestamps according to deployment policy.
- Reset corrections and superseded estimates remain auditable and exportable until explicit owner data
  erasure.
