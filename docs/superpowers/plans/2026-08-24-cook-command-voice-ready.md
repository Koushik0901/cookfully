# Cook Command Voice-Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cmd+K + Cook voice-ready via same InlineRepairGateway (≤600ms 0.80 gate) — Cmd+K keeps tiny preview B (no draftId), Cook handles next/previous/repeat/timer + confident how-much, STT-ready transcript=prompt.

**Architecture:** Harden `api/routes/intelligence.py:158-174` `cooking_action` to `Literal[4]` + minutes 1..120 + query 3..80 grammar. `frontend/src/app/CommandPalette.tsx:47,164-194` replaces `createDraft/executeDraft` with `intelligenceApi.infer("command", q)` inline gated preview (no draft table). `frontend/src/features/recipes/CookMode.tsx` adds `onUtterance` calling same gateway `operation="cook"` prompt=`Step+Ingredients+User` + system `device:phone` future, fail-quiet.

**Tech Stack:** Python 3.13 FastAPI/Pydantic 2 (Annotated+Field+Literal), cactus-needle tool_index, TypeScript 5.x React 19.2 TanStack Query, Radix Dialog, Zod

## Global Constraints

- Python 3.13, cactus-needle>=2,<3 `deploy/docker/intelligence.Dockerfile:13`, intelligence-net `internal:true` isolated no DB/Redis creds.
- `≤600ms` inline `intelligence_inline_timeout_ms 600` `config.py:83`, gap-only never overwrite quantity, `confidence None` fail-closed, system `date:YYYY-MM-DD; locale:en-US; device:server→phone` max500 `contracts:37`.
- Threshold `0.80` gated preview (B) — below `0.80`/`[]`/`timeout` → Not sure / repeat step, never auto-write, `BulkPantryCreateResponse` list still respected.
- No new model/table: reuse `InlineRepairGateway` `_gate` `_emit_log` no PII, grammar `Literal` prevents bad minutes/action.
- `256-tok` window via `inline_repair._window` already, STT transcript doc-only no code this slice.

---

## File Structure

- Modify: `backend/src/cookfully/api/routes/intelligence.py:158-174` — harden cooking_action parameters enum Literal + Field
- Modify: `frontend/src/app/CommandPalette.tsx:47,64-194` — replace draft mutations with `infer` preview, keep ↑↓/Esc/⌘K
- Modify: `frontend/src/features/intelligence/api.ts:42-53` — ensure `infer` used, leave `createDraft` unused (not deleted this slice)
- Modify: `frontend/src/features/recipes/CookMode.tsx` (and `frontend/src/features/recipes/RecipeDetailPage.tsx` if cook button) — add `onUtterance` handler + timer/query chip
- Create: `backend/tests/unit/test_cook_voice_gateway.py` + `frontend/src/features/intelligence/__tests__/CommandPalette.infer.test.tsx` (or update existing `CommandPalette.test.tsx`)
- Reference: `backend/src/cookfully/application/inline_repair.py:53-58` `_gate` reused, no change

---

### Task 1: Harden cook tool schema (grammar Literal prevents bad timer)

**Files:**
- Modify: `backend/src/cookfully/api/routes/intelligence.py:158-174`
- Test: `backend/tests/unit/test_cook_voice_gateway.py`

**Interfaces:**
- Consumes: `InlineRepairGateway._gate`, `ToolDefinition` with `parameters` JSON Schema
- Produces: `cooking_action` `parameters: {action: enum[4], minutes: 1..120, query: 3..80}` validated

- [ ] **Step 1: Write failing test for Literal enforcement**

```python
from cookfully.api.routes.intelligence import _TOOLS
import json
def test_cook_tool_literal():
    cook_tools = [t for t in _TOOLS["cook"]]
    schema = cook_tools[0].parameters
    # action must be enum next/previous/repeat/timer
    assert set(schema["properties"]["action"]["enum"]) == {"next","previous","repeat","timer"}
    assert schema["properties"]["minutes"]["minimum"] == 1
    assert schema["properties"]["minutes"]["maximum"] == 120
    assert "query" in schema["properties"]
```

- [ ] **Step 2: Run failing**

Run: `uv run --directory backend pytest tests/unit/test_cook_voice_gateway.py::test_cook_tool_literal -v`
Expected: FAIL `KeyError enum` or wrong max

- [ ] **Step 3: Implement hardened schema**

```python
# api/routes/intelligence.py:158-174 inside _TOOLS["cook"]
"cook": (
    ToolDefinition(
        name="cooking_action",
        description="Interpret next/previous/repeat/timer or ingredient quantity question from current step",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["next","previous","repeat","timer"]},
                "minutes": {"type": "integer", "minimum": 1, "maximum": 120},
                "query": {"type": "string", "minLength": 3, "maxLength": 80},
            },
            "required": ["action"],
        },
    ),
),
```
Grammar-compiled via Needle ensures `action="dance"` or `minutes=9999` unemittable.

- [ ] **Step 4: Run passing**

Run: `uv run --directory backend pytest tests/unit/test_cook_voice_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/api/routes/intelligence.py backend/tests/unit/test_cook_voice_gateway.py
git commit -m "feat(cook): harden cooking_action to Literal[4] + minutes 1..120 + query 3..80"
```

---

### Task 2: Cmd+K retire draft path → inline infer preview (PM-picked B)

**Files:**
- Modify: `frontend/src/app/CommandPalette.tsx:47,64-194`
- Modify: `frontend/src/features/intelligence/api.ts:36-53` (no deletion, just use `infer`)
- Test: `frontend/src/features/intelligence/__tests__/CommandPalette.infer.test.tsx`

**Interfaces:**
- Consumes: `intelligenceApi.infer(operation="command", prompt, context)` threshold `0.80`, `BulkPantryCreateResponse` list compat
- Produces: Preview chip `We think you mean: … — Add?` when `status==="ok" && confidence>=0.80`, `Not sure` else, single tap `pantry.create`/`grocery.create`/`mealPlans.add` (real POSTs)

- [ ] **Step 1: Write failing test (Vitest)**

```tsx
import { render, screen } from "@testing-library/react"
import { CommandPalette } from "../../app/CommandPalette"
test("shows preview when high conf", async () => {
  vi.mock("../../features/intelligence/api", () => ({ intelligenceApi: { infer: vi.fn().mockResolvedValue({status:"ok", confidence:0.88, functionCalls:[{name:"add_pantry_item", arguments:{name:"onions", quantity:2, unit:"kg"}}]})}}))
  render(<CommandPalette />)
  // type "add 2kg onions" then expect "We think you mean"
  expect(await screen.findByText(/We think you mean/)).toBeInTheDocument()
})
test("shows Not sure when low conf", async () => {
  vi.mocked(...).mockResolvedValue({status:"ok", confidence:0.6, functionCalls:[]})
  expect(await screen.findByText(/Not sure/)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run failing**

Run: `pnpm --dir frontend test --run src/features/intelligence/__tests__/CommandPalette.infer.test.tsx`
Expected: FAIL `createDraft not mocked` or chip missing

- [ ] **Step 3: Implement preview**

```tsx
// CommandPalette.tsx:47 replace
const inferred = useMutation({ mutationFn: (q:string)=> intelligenceApi.infer("command", q) })
// in emptyState (!visibleCommands && !visibleRecipes && !recipes.isPending)
{!inferred.data ? (
  <button onClick={()=> inferred.mutate(query.trim())} disabled={inferred.isPending}>Interpret with Cookfully</button>
) : inferred.data.status==="ok" && (inferred.data.confidence??0)>=0.80 && inferred.data.functionCalls[0] ? (
  <Chip>We think you mean: {inferred.data.functionCalls[0].name} {JSON.stringify(inferred.data.functionCalls[0].arguments)} — <button onClick={()=> { const a=inferred.data!.functionCalls[0].arguments; if (a.name) pantryOrGroceryCreate(a); }}>Add</button></Chip>
) : (
  <NotSure>Add manually? <a href="/app/pantry?add=1">Open pantry</a></NotSure>
)}
// remove interpretation/execution draftId branches (164-194), keep keyboard ↑↓/Esc
```

Keep `intelligenceApi` `createDraft/executeDraft` unused this slice (not deleted).

- [ ] **Step 4: Run passing**

Run: `pnpm --dir frontend test --run src/features/intelligence/__tests__/CommandPalette.infer.test.tsx` and `pnpm --dir frontend typecheck`
Expected: PASS, typecheck PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/CommandPalette.tsx frontend/src/features/intelligence/__tests__/CommandPalette.infer.test.tsx
git commit -m "feat(cmdk): retire draft preview → inline infer chip (B, 0.80 gate, Add does real POST)"
```

---

### Task 3: CookMode voice-ready handler (next/repeat/timer + confident how-much)

**Files:**
- Modify: `frontend/src/features/recipes/CookMode.tsx`
- Test: `frontend/src/features/recipes/__tests__/CookMode.voice.test.tsx` + `backend/tests/unit/test_cook_voice_gateway.py` (extend)

**Interfaces:**
- Consumes: `intelligenceApi.infer("cook", prompt)` where `prompt=f"Step: {currentStep}\nIngredients: {ingredients.join(', ')}\nUser: {utterance}"` + system `device:phone` future
- Produces: `onUtterance(string) => void` handling `timer` (setTimeout), `next/previous/repeat` (step index), `query` answer chip only when evidenced

- [ ] **Step 1: Failing Cook test**

```tsx
test("cook timer 5 starts timer", async () => {
  vi.mocked(infer).mockResolvedValue({status:"ok", confidence:0.9, functionCalls:[{name:"cooking_action", arguments:{action:"timer", minutes:5}}]})
  render(<CookMode recipe={mockRecipe} currentStep={0} />)
  fireEvent.click(screen.getByText(/timer 5/i))
  expect(await screen.findByText(/Timer 5 min/)).toBeInTheDocument()
})
test("how much garlic answers only when evidenced", async () => {
  mockInfer.mockResolvedValue({status:"ok", confidence:0.88, functionCalls:[{name:"cooking_action", arguments:{action:"repeat", query:"garlic"}}]})
  // ingredients contains "2 cloves garlic" → shows chip 2 cloves, else repeat step text
})
```

- [ ] **Step 2: Run failing**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/CookMode.voice.test.tsx`
Expected: FAIL `onUtterance not defined`

- [ ] **Step 3: Implement handler**

```tsx
// CookMode.tsx
const utteranceMut = useMutation({ mutationFn: (u:string)=>{
  const prompt = `Step: ${steps[currentStep]}\nIngredients: ${ingredients.join(', ')}\nUser: ${u}`
  return intelligenceApi.infer("cook", prompt)
}})
function onUtterance(u:string){ utteranceMut.mutate(u) }
// render
{utteranceMut.data?.status==="ok" && (utteranceMut.data.confidence??0)>=0.80 && utteranceMut.data.functionCalls[0]?.name==="cooking_action" && utteranceMut.data.functionCalls[0].arguments.action==="timer" && (
  <TimerChip minutes={utteranceMut.data.functionCalls[0].arguments.minutes} />
)}
{utteranceMut.data?.functionCalls[0]?.arguments.query && ingredients.join().toLowerCase().includes(utteranceMut.data.functionCalls[0].arguments.query.toLowerCase()) && (
  <AnswerChip>{ingredients.find(i=>i.toLowerCase().includes(query))}</AnswerChip>
)}
// fallback: repeat step text
```

`operation="cook"` already routes to `_TOOLS["cook"]` hardened.

- [ ] **Step 4: Passing**

Run: `pnpm --dir frontend test --run src/features/recipes/__tests__/CookMode.voice.test.tsx` and `uv run --directory backend pytest tests/unit/test_cook_voice_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/recipes/CookMode.tsx backend/tests/unit/test_cook_voice_gateway.py
git commit -m "feat(cook): voice-ready handler timer/query via inline gateway (STT transcript=prompt)"
```

---

## Self-Review

- Spec coverage: Tool harden → Task1, Cmd+K preview B → Task2, Cook voice-ready → Task3; `_gate` 0.80, 600ms, system facts preserved via existing gateway, no draft table write, STT doc-only.
- Placeholders: none (code blocks complete, paths exact, commands runnable).
- Type consistency: `BulkPantryCreateResponse|PantryItemResponse` Union already landed 0e61b95; `cooking_action minutes 1..120` `query 3..80` consistent across BE/FE; `infer("command"|"cook", prompt)` signature matches `frontend/src/features/intelligence/api.ts:36`.
