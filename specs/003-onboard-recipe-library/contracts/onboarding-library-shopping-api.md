# Cookfully API Contract: Onboarding, recipe organization, photos, and shopping

All endpoints are owner-scoped, use the existing browser session and CSRF protections for browser mutations, and return the established problem format on validation, authorization, stale-version, or conflict failures. Existing recipe, grocery, export, and erasure contracts remain compatible unless listed below.

## Owner onboarding

| Method and path | Request | Successful response | Notes |
|---|---|---|---|
| `GET /api/v1/owner/onboarding` | None | `OnboardingState` | Returns `state`, optional `firstAction`, optional `resolvedAt`, and `version`. Missing storage is represented as the default pending state. |
| `PUT /api/v1/owner/onboarding` | `state` (`completed` or `dismissed`), optional `firstAction`, `version` | `OnboardingState` | Requires an explicit version; cannot return an owner to pending. |

## Recipe photos

| Method and path | Request | Successful response | Notes |
|---|---|---|---|
| `PUT /api/v1/recipes/{recipeId}/photo` | `multipart/form-data` with one `photo` file; `If-Match` recipe version | `RecipeDetail` | Accepts JPEG, PNG, or WebP only. The server decodes, dimensions-checks, and normalizes the image before changing the active photo. |
| `DELETE /api/v1/recipes/{recipeId}/photo` | `If-Match` recipe version | `RecipeDetail` | Removes only the active photo relation. Recipe content and nutrition are unchanged. |

An upload/replace failure returns a problem response and leaves the previously active photo intact. `Recipe` and `RecipeDetail` continue to expose `imageUrl` as the private media route.

## Recipe organization

| Method and path | Request | Successful response | Notes |
|---|---|---|---|
| `GET /api/v1/recipe-collections` | None | ordered `RecipeCollection[]` | Includes each collection's recipe count. |
| `POST /api/v1/recipe-collections` | `name`, optional `position` | `RecipeCollection` | Rejects blank or duplicate names for the owner. |
| `PATCH /api/v1/recipe-collections/{collectionId}` | `name` and/or `position`; `If-Match` | `RecipeCollection` | Supports rename and reorder. |
| `DELETE /api/v1/recipe-collections/{collectionId}` | `If-Match` | `204` | Removes memberships only. |
| `PUT /api/v1/recipes/{recipeId}/organization` | `favorite`, `collectionIds`, `mealRoles`; `If-Match` | `RecipeDetail` | Replaces only organization data, validates collection ownership and the four allowed roles, and does not recalculate nutrition. |
| `GET /api/v1/recipes` | existing filters plus optional `favorite`, `collectionId`, `mealRole` | `RecipePage` | Filters compose with search and existing archive/readiness behavior. |

`Recipe` and `RecipeDetail` add `favorite`, ordered `collections`, and `mealRoles`. Collection names are displayed only in organization contexts; recipe discovery cards remain food-first.

## Shopping stops and grocery completion

| Method and path | Request | Successful response | Notes |
|---|---|---|---|
| `GET /api/v1/grocery-shopping-stops` | None | ordered `GroceryShoppingStop[]` | Returns the owner's stops. |
| `POST /api/v1/grocery-shopping-stops` | `name`, optional `position` | `GroceryShoppingStop` | Creates a personal stop. |
| `PATCH /api/v1/grocery-shopping-stops/{stopId}` | `name` and/or `position`; `If-Match` | `GroceryShoppingStop` | Supports rename/reorder. |
| `DELETE /api/v1/grocery-shopping-stops/{stopId}` | `If-Match` | `204` | Clears item assignments and remembered placements; never deletes grocery items. |
| `PATCH /api/v1/grocery-items/{itemId}` | existing fields plus optional `shoppingStopId` and `rememberPlacement`; `If-Match` | `GroceryItem` | `rememberPlacement` is allowed only for a safe generated item. |
| `POST /api/v1/meal-plans/{weekStart}/grocery-list/complete` | `If-Match` list version | `GroceryList` | Fails when any item is unchecked. |
| `POST /api/v1/meal-plans/{weekStart}/grocery-list/reopen` | `If-Match` list version | `GroceryList` | Makes a completed list active again; it is the only way to regenerate the same completed pass. |

`GroceryList` adds nullable `completedAt`; `GroceryItem` adds nullable `shoppingStop`. Existing `POST` regeneration rejects a completed list with a recoverable conflict until it is reopened. List responses retain item sources, manual state, checked state, needs-review state, and pantry-deduction behavior.

## Generated client and structured access

The OpenAPI document and generated frontend schema are regenerated from these contracts. Recipe organization and grocery completion remain available through the canonical application services. Any MCP read additions must reuse these services and preserve the same owner boundary; no new MCP mutation is required for this UI-focused slice.
