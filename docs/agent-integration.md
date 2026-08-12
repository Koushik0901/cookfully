# Agent integration

Cookfully exposes a deliberately narrow Model Context Protocol (MCP) surface for recipe,
meal-plan, goal, and grocery workflows. It is a planning aid, not medical advice. Nutrition values
may be estimated, partial, source-provided, or manually corrected; clients must preserve the
reported state, coverage, provenance, nulls, and immutable meal-plan snapshots.

## Create and revoke access

Sign in as the owner and open **Agent access** at `/app/agent-access`. Name the connection, select
only the scopes it needs, optionally set an expiry, and create the token. The `cookfully_...` secret is
shown exactly once. Store it in the MCP client's secret store; Cookfully stores only its SHA-256
hash and cannot recover it.

The equivalent owner-session HTTP endpoints are:

- `GET /api/v1/access-tokens` — list metadata; never returns secrets.
- `POST /api/v1/access-tokens` — create a token and return its secret once.
- `DELETE /api/v1/access-tokens/{tokenId}` — revoke immediately; requires an
  `Idempotency-Key` header of 16–128 characters.

Token management accepts browser-session authentication only. A bearer token cannot create,
inspect, or revoke other tokens. Revoked and expired tokens fail closed on their next request.

## Connect an MCP client

Use the Streamable HTTP endpoint at `https://YOUR_HOST/mcp` with:

```text
Authorization: Bearer cookfully_YOUR_ONE_TIME_SECRET
Accept: application/json, text/event-stream
```

The server is stateless at the transport layer and uses the official Python MCP SDK. It exposes no
prompt templates and no general chat tool. Configure the public API host correctly so the SDK's DNS
rebinding protection can validate the `Host` header.

## Scopes and tools

| Scope | Tools |
| --- | --- |
| `goals:read` | `get_current_goals` |
| `recipes:read` | `find_recipes` |
| `plans:read` | `get_meal_plan`, `get_period_totals` |
| `plans:write` | `add_recipe_to_plan`, `update_meal_plan_entry`, `remove_meal_plan_entry` |
| `grocery:read` | `get_grocery_list` |
| `grocery:write` | `regenerate_grocery_list` |

Read-only scopes are the recommended starting point. Write scopes must be selected explicitly.
Every tool checks its own declared scope; a token cannot use endpoints or tools that omit a scope.
Limits are per token and per minute: 120 ordinary reads, 30 searches, and 20 mutations.

### Complete plan reads

Call `get_meal_plan` with `week_start` in `YYYY-MM-DD` form. The response is the same representation
as `GET /api/v1/meal-plans/{weekStart}`: dated entries, serving quantities, immutable display
nutrition snapshots, origin, entry and plan versions, day/week totals, target differences, and
grocery status. This exact parity is intentional; clients must not recalculate totals from rounded
display values.

## Exact decimals and unavailable values

Nutrient, quantity, serving, tolerance, and target-difference values are canonical JSON strings,
never binary floating-point numbers. For example, use `"1.5"`, not `1.5`. Display snapshots retain
the HTTP contract's round-half-up precision. `null` means unavailable and must not be interpreted as
zero. Corrections and provenance labels remain visible through the same application-query layer used
by the web UI.

## Safe writes

Every mutation requires a unique `idempotency_key` of 16–128 characters. Replaying the same key and
payload returns the original result; reusing a key for another payload returns an idempotency
conflict. Updates and removals also require the current `expected_version`. On `stale_version` or
`version_conflict`, reload the resource and ask the owner before retrying with the new version.
Externally created plan entries are recorded with origin `external` and a correlation ID. Structured
errors contain bounded codes and messages without SQL, stack traces, provider payloads, or secrets.

## Resources

- `cookfully://methodology/nutrition` explains estimates, coverage, provenance, correction
  precedence, snapshots, null handling, and limitations.
- `cookfully://schema/export/{version}` documents the portable export schema; `v1` is supported.

## Inspector validation

With a read token in the environment, start the
[official MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) and connect to the
Streamable HTTP URL:

```powershell
$env:COOKFULLY_MCP_TOKEN = "cookfully_YOUR_ONE_TIME_SECRET"
npx @modelcontextprotocol/inspector
```

Set the transport to **Streamable HTTP**, URL to `http://localhost:8000/mcp`, and add the
`Authorization: Bearer ...` header from the environment-backed secret. Validate:

1. `tools/list` contains exactly the nine documented tools.
2. `prompts/list` is empty.
3. `get_meal_plan` exactly matches a web/API reload for the same week, including decimal strings,
   snapshot state, origin, versions, and totals.
4. A write made with a write-scoped token appears after reloading the web planner and has origin
   `external`.
5. A read-only token receives structured `insufficient_scope`; a revoked token receives HTTP 401.
6. Both documentation resources can be listed and read.

Automated contract and end-to-end tests run the same read, write, reload, revocation, rate-limit,
idempotency, stale-version, and exact-parity checks used for release validation.
