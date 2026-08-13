# Data Model: A calmer first kitchen

## Owner onboarding state

One record per owner, distinct from account preferences.

| Field | Rules | Purpose |
|---|---|---|
| `owner_id` | primary key; references the owner account; cascade delete | Maintains the existing single-owner boundary and makes export/erasure scope explicit. |
| `state` | `pending`, `completed`, or `dismissed`; defaults to `pending` | Determines whether first-run guidance is shown. |
| `first_action` | optional; `manual_recipe`, `import_recipe`, or `view_plan` | Preserves optional context without changing the owner's permissions or nutrition guide. |
| `resolved_at` | null while pending; UTC timestamp otherwise | Records when blocking first-run guidance stopped. |
| `version` | positive integer | Supports explicit conflict handling. |

**Transitions**: `pending -> completed` after the owner completes a selected first action; `pending -> dismissed` when they skip it; `completed` and `dismissed` remain terminal unless an owner-facing future reset feature is explicitly specified. A failed state write leaves normal Recipes/Plan access available.

## Recipe photo

No second photo table is required. The existing `recipes.image_asset_id` remains the sole active representative image and points to an existing `media_assets` row with kind `recipe_image`.

| Field / relation | Rules | Purpose |
|---|---|---|
| `recipes.image_asset_id` | nullable; points only to an accepted recipe image | The one active image shown in recipe surfaces. |
| `media_assets.recipe_id` | references the same recipe; cascade delete | Keeps media in export and erasure scope. |
| `media_assets.content_type`, `byte_size`, `sha256`, `storage_key` | populated by the existing normalized image service | Provides safe display, deduplication, and portable-media integrity. |

**Lifecycle**: no image -> browser-local preview -> one saved normalized image -> replaced image or no image. Upload failure never changes `image_asset_id`; removal clears the relation and uses existing fallback art. Replacing/removing increments recipe version but does not modify recipe content, nutrition state, estimates, corrections, or input hash.

## Recipe organization

### Recipe favorite

Add `is_favorite` to `recipes`, default false and indexed with active recipe discovery as appropriate. It is owner-scoped through the single-owner recipe collection and is independent of archive/nutrition lifecycle.

### Recipe collection

| Field | Rules | Purpose |
|---|---|---|
| `id` | UUID primary key | Stable collection identity. |
| `owner_id` | owner account foreign key; cascade delete | Explicit ownership. |
| `name` | trimmed, case-insensitively unique per owner, 1–80 characters | Human-readable optional grouping. |
| `position` | non-negative, unique per owner | Stable owner-controlled order. |
| `version` | positive integer | Rename/reorder/delete conflict control. |

### Recipe collection membership

Composite uniqueness on `collection_id` and `recipe_id`; both cascade on deletion. A recipe can have zero or more memberships. No membership owns, archives, deletes, or changes a recipe.

### Recipe meal role

One row per `(recipe_id, role)`, where `role` is exactly `breakfast`, `lunch`, `dinner`, or `snack`. No owner-created role vocabulary or additional attributes are introduced. Roles do not affect meal plan entries or nutrition.

## Grocery shopping stop

| Field | Rules | Purpose |
|---|---|---|
| `id` | UUID primary key | Stable shopping-stop identity. |
| `owner_id` | owner account foreign key; cascade delete | Keeps stops personal. |
| `name` | trimmed, case-insensitively unique per owner, 1–80 characters | Owner's actual shopping destination. |
| `position` | non-negative, unique per owner | Controls list order. |
| `version` | positive integer | Rename/reorder/delete conflict control. |

`grocery_items.shopping_stop_id` is nullable. Deleting a stop sets this relation to null rather than deleting an item. Reconciliation carries the relation forward for a matched item.

## Remembered grocery placement

| Field | Rules | Purpose |
|---|---|---|
| `owner_id` | part of unique identity; references owner account | Owner-scoped preference. |
| `normalized_food_name` | part of unique identity; canonical generated-item name | Only deterministic, stable generated identity may be remembered. |
| `shopping_stop_id` | references a current shopping stop; cascade delete | Applies destination order to future safe matches. |
| `updated_at` | UTC timestamp | Supports predictable last-choice behavior. |

The service creates or updates this preference only when an owner explicitly chooses to remember a placement for a non-ambiguous generated item. It is not applied to manual grocery items, items with manual names, or generated items marked `needs_review`.

## Shopping pass

Extend the existing `grocery_lists` lifecycle.

| Field | Rules | Purpose |
|---|---|---|
| `status` | existing `current`, `dirty`, `generating`, `failed`, plus `completed` | Distinguishes an active list from a preserved finished trip. |
| `completed_at` | null unless status is `completed` | Records the finish time. |
| `version` | positive integer | Guards complete/reopen and list updates. |

**Transitions**: absent -> generating -> current; current/dirty/failed -> generating -> current; current with every item checked -> completed; completed -> current only through explicit reopen. Plan changes do not mark a completed list dirty. Regeneration of a completed list is rejected until the owner reopens it.

## Ownership, export, and erasure

All newly introduced tables use direct owner foreign keys where possible. Recipe organization is tied to recipes in the current single-owner model. Export includes onboarding, collection, membership, role, shopping-stop, remembered-placement, grocery-list completion, grocery item assignment, and referenced unencrypted media rows. Full-owner erasure includes database rows and recipe-photo files through the existing media quarantine process.
