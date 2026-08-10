# MCP Tool Contract (Expansion P5)

## Boundary

The MCP server uses the official Python SDK and Streamable HTTP. It authenticates a scoped token and
calls the same application commands/queries as `/api/v1`; it does not query tables or reproduce
nutrition calculations. Tool results use the same identifiers, decimal rounding, provenance labels,
nutrition states, conflict versions, and failure codes as OpenAPI responses.

## Tools

### `get_current_goals`

- **Scope**: `goals:read`
- **Input**: optional local `on_date` (`YYYY-MM-DD`)
- **Output**: effective goal, optional meal targets, version, and macro-derived calorie difference
- **Errors**: `goal_not_found`, `invalid_date`

### `get_period_totals`

- **Scope**: `plans:read`
- **Input**: `week_start`; optional `local_date` and `meal_slot`
- **Output**: selected meal/day/week totals, targets, differences, nutrition state, coverage ratio,
  and contributing entry IDs
- **Errors**: `plan_not_found`, `invalid_week_boundary`

### `find_recipes`

- **Scope**: `recipes:read`
- **Input**: optional text query, calorie/macro minimums and maximums, nutrition states, archived flag,
  cursor, and limit
- **Output**: paginated recipes with per-serving values, provenance summary, and version
- **Errors**: `invalid_constraint`, `cursor_expired`

### `add_recipe_to_plan`

- **Scope**: `plans:write`
- **Input**: `recipe_id`, `week_start`, `local_date`, `meal_slot`, `servings`, required
  `idempotency_key`, optional expected plan version
- **Output**: created entry with immutable nutrition snapshot plus updated day/week totals
- **Errors**: `recipe_not_found`, `nutrition_unavailable`, `date_outside_week`, `version_conflict`,
  `idempotency_conflict`

### `update_meal_plan_entry`

- **Scope**: `plans:write`
- **Input**: `entry_id`, changed date/slot/servings, required `expected_version` and
  `idempotency_key`; `refresh_nutrition` defaults false
- **Output**: updated entry and totals
- **Errors**: `entry_not_found`, `version_conflict`, `invalid_servings`, `idempotency_conflict`

### `remove_meal_plan_entry`

- **Scope**: `plans:write`
- **Input**: `entry_id`, `expected_version`, `idempotency_key`
- **Output**: removal confirmation, updated totals, and grocery-list status
- **Errors**: `entry_not_found`, `version_conflict`, `idempotency_conflict`

### `get_grocery_list`

- **Scope**: `grocery:read`
- **Input**: `week_start`
- **Output**: status, generation time, items, units, review flags, checked state, and recipe sources
- **Errors**: `list_not_found`, `plan_not_found`

### `regenerate_grocery_list`

- **Scope**: `grocery:write`
- **Input**: `week_start`, required `idempotency_key`, optional expected plan/list versions
- **Output**: reconciled list with preserved manual/check state and review flags
- **Errors**: `plan_not_found`, `version_conflict`, `idempotency_conflict`

## Resources

- `vigor-vine://methodology/nutrition` — versioned explanation of estimates, provenance, coverage,
  correction precedence, and limitations.
- `vigor-vine://schema/export/{version}` — portable export schema documentation.

The server exposes no prompt templates and no general chat tool.

## Safety Rules

- Tokens default to read-only. Write scopes require explicit creation by the owner.
- Mutating tools require idempotency keys and optimistic versions where a record already exists.
- Tool descriptions MUST state that nutrition values are planning estimates, not medical advice.
- Tool output MUST distinguish null/unavailable from numeric zero.
- Errors MUST be structured and MUST NOT expose stack traces, SQL, secrets, raw provider payloads, or
  unrelated personal data.
- Rate limits are per token and stricter for search and mutations than local browser reads.

## Contract Tests

Each tool is tested against the corresponding application command/query and OpenAPI representation.
Given identical state, normalized MCP and HTTP outputs MUST match for values, provenance, versions,
nutrition states, and failure codes.
