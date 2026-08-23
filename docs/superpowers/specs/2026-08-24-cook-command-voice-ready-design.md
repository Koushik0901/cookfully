# Cook Command Voice-Ready — Design

Date: 2026-08-24
Status: Approved (brainstormed 2026-08-24, Approach 1: Preview-preserving gateway reuse, voice-ready)
Branch: `cook-command-voice` (worktree `.worktrees/cook-command-voice`)
Spec: This file | Plan to follow `docs/superpowers/plans/2026-08-24-cook-command-voice-ready.md`
Related: `docs/superpowers/specs/2026-08-23-needle2-inline-repair-design.md` (gateway), `docs/superpowers/specs/2026-08-24-make-inline-repair-live-design.md` (1+2+3), `backend/src/cookfully/application/inline_repair.py:47-331`, `backend/src/cookfully/api/routes/intelligence.py:158-174`, `frontend/src/app/CommandPalette.tsx:47,164-194`, `frontend/src/features/intelligence/api.ts:42-53`, `backend/src/cookfully/intelligence/service.py:68-80`
Model: Needle2 `needle2.cact` 45M/14MB, grammar-constrained, confidence-calibrated, 256-tok window

## Problem

Import/pantry are live invisible (`InlineRepairGateway` `≤600ms` `0.80` gap-only) but two surfaces still use legacy draft echo: `CommandPalette` `createDraft("command")` → `draftId/expiresAt` → `executeDraft` (`frontend/src/app/CommandPalette.tsx:164-194`, `frontend/src/features/intelligence/api.ts:42-53`) shows raw `call.name` + `Confirm` before write, and Cook Mode `cooking_action` (`api/routes/intelligence.py:158-174`) echoes `{"name":"cooking_action",…arguments}` with no timer/quantity logic. No STT runway — a future speech transcript would need a new model path.

## Goal

Make Cmd+K + Cook voice-ready with **nothing new to see**: Cmd+K keeps the tiny preview the PM picked (`“We think you mean: add 2kg onions to pantry — Add?”` B) but via the same `InlineRepairGateway` (`command` `600ms` `0.80` gated, no `intelligence_drafts` table); Cook understands `next/previous/repeat/timer` + confident `how much X?` from the current recipe only when evidenced. One gateway for 3 callers (palette, cook, future STT `transcript → prompt`).

Non-goals: No STT/mic code, no bulk endpoint change, no threshold change (`0.80`), no `intelligence_drafts` deletion this slice (just retired from UI).

## Architecture

```
Cmd+K typed text ──┐
                    ├─ InlineRepairGateway (single) ─ 600ms gate 0.80 ─ preview chip → real POST
Cook utterance ─────┤   tools: OneSchema Literal[4] + minutes/query  system: date:…; locale:…; device:server→phone
Future STT transcript┘   operation: command (palette) | cook (mode)   draft path retired
```

* **Cmd+K** (`frontend/src/app/CommandPalette.tsx`) → `intelligenceApi.infer("command", typedQuery)` (`frontend/src/features/intelligence/api.ts:42`) inline, no `createDraft`. Below `0.80`/`[]`/`timeout` → `“Not sure — add manually?”` never writes.
* **Cook Mode** (`frontend/src/features/recipes/CookMode.tsx`) → same gateway `operation="cook"` `prompt="Step: {currentStep}\nIngredients: {ingredients.join(', ')}\nUser: {utterance}"` + `system` `device: phone` (future voice) — gateway stays model-only `intelligence-net` (`compose.yaml`).
* **STT hook (future, no code):** `transcript string` → same `operation="cook"` `prompt` → same `cooking_action` return → `next/timer/query` execution. Noted in spec, not built.

## Components

* **`api/routes/intelligence.py:158-174`** — harden `cooking_action` `parameters` to `{action: enum[next,previous,repeat,timer], minutes: 1..120, query: 3..80}` (`Literal` grammar, `needlesh grammar-compiled`). Keep `command` tools (`add_pantry_item`, `add_grocery_item`, `add_recipe_to_plan`, `search_recipes`) unchanged.
* **`application/inline_repair.py`** — keep `InlineRepairGateway` (`_gate` `confidence is None` fail-closed, `_emit_log` no PII, `600ms` timeout). Add trivial helper `def _gate_ok(resp: InferenceResponse, threshold=0.80) -> bool` reused by both surfaces; no new schema (reuses `IngredientRowSchema` allowlist for `minutes` range via gateway validation).
* **`frontend/src/app/CommandPalette.tsx:47,164-194`** — replace `interpretation = useMutation(createDraft)` + `execution = useMutation(executeDraft)` with `const inferred = useMutation((q)=>intelligenceApi.infer("command", q))`; render preview chip from `inferred.data.functionCalls[0]` (not `draftId`). Keep keyboard `↑↓`/`Esc`/`⌘K`.
* **`frontend/src/features/recipes/CookMode.tsx`** — add `onUtterance(utterance: string)` handler calling `intelligenceApi.infer("cook", prompt)` via gateway threshold; handle `timer` (start `setTimeout`) vs `query` answer chip.

## Data flow

1. `requestId="palette-{correlation_id}"` or `"cook-{id}"` `operation=command|cook` `prompt=typedQuery | step+utterance` `system="date:YYYY-MM-DD; locale:en-US; device:server"` `tools=(OneSchema Literal)` `context={}`.
2. `await wait_for(to_thread(client.infer, timeout_seconds=0.60), timeout=0.60)` `except (TimeoutError, asyncio.TimeoutError): return Not sure` (`import_preview.py:168` pattern).
3. `_gate` `status!="ok" or !function_calls or confidence is None or <0.80` → `Not sure` / `repeat step` (no write, `needle_inline applied=false` log).
4. Above → Cmd+K preview chip shows `We think you mean: {display from args} — Add?` → tapping `Add` does real `POST /pantry-items` (bulk list-aware `BulkPantryCreateResponse`) `POST /grocery-items` etc via existing services; Cook `timer` starts, `query` shows answer chip only when `args.query` span evidenced in `ingredients[]` (gap check `query in ingredients.join`).
5. No `intelligence_drafts` write; old `api/routes/intelligence.py:247-293` `createDraft` stays but unused until removed next release.

## Cmd+K preview shape (PM-picked B)

```tsx
// palette emptyState already: !visibleCommands && !visibleRecipes
const { mutate: infer, data, isPending } = useMutation((q:string)=>intelligenceApi.infer("command", q))
if (data?.status==="ok" && (data.confidence??0)>=0.80 && data.functionCalls[0]?.name==="add_pantry_item") {
  return <Chip>We think you mean: add {data.functionCalls[0].arguments.name} to pantry — <button onClick={()=> pantry.create(data.functionCalls[0].arguments)}>Add</button></Chip>
}
if (data?.status==="unsupported" || (data.confidence??0)<0.80) return <NotSure>Add manually?</NotSure>
```

No `draftId`, no `expiresAt`.

## Cook voice-ready shape

* Tool: `action: Literal[4]` + `minutes`/`query` hard-capped, grammar prevents `minutes=9999`/`action="dance"` (unemittable).
* Cook prompt construction (deterministic, ≤256 chars via existing `_window`):
```
prompt = f"Step: {currentStep}\nIngredients: {', '.join(ingredients)}\nUser: {utterance}"
```
`_window(prompt)[0]` same as import/pantry.

* STT future: `transcript="(utterance)"` → identical path, no model change.

## Testing

* Unit: `test_cmd_preview_shows_when_high_conf` (`confidence 0.88` `add_pantry_item` → preview + Add), `test_cmd_no_preview_when_low` (`0.60` → Not sure, no write), `test_cook_timer_and_query` (`next→next`, `timer 5→minutes 5`, `how much garlic→query garlic` only when evidenced in `ingredients` else repeat).
* Contract: `POST /intelligence/infer operation=cook` still `Literal` gated, no draft id leaked.
* Existing 28+ unit `inline_*`/`pantry_inline` stay pass; `ruff format --check .`, `ruff check .`, `mypy src` clean.

## Risks & non-goals

* No STT dep, no draft deletion — old `intelligence_drafts` table stays dormant for one release (easy rollback).
* Threshold stays `0.80`; voice latency same `600ms` — STT adds its own latency budget later, not in this slice.

## Phasing

This slice `A` (palette preview + cook voice-ready) lands now; slice `B` (hardware needle sweep + Playwright bulk perf + prod canary `INLINE_ENABLED 5%→100%`) follows and can reuse the same gateway no change.
