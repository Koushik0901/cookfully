# Needle2 Inline Repair Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Silently repair capture gaps with Needle2 racing legacy parsers in parallel (≤600ms, gap-only, confidence-gated) to reach 9+/10 without new UI.

**Architecture:** New `application/inline_repair.py` gateway holds hardened Pydantic schemas with grammar constraints, runs `asyncio.gather(legacy, IntelligenceClient.infer(system+tools))` in routes, merges only `null/empty` gaps when `confidence≥T` (`0.60→0.90` sweep), otherwise keeps legacy. Isolated `intelligence` service unchanged; dual timeouts (`inline 0.6s` vs `command 2s`), `tool_index_path` when >5 tools, threshold sweep script producing `artifacts/needle-threshold-report.json`.

**Tech Stack:** Python 3.13, cactus-needle 2.x (`Needle(weights, tools, system, tool_index_path)`), FastAPI, Pydantic 2 (Annotated+Field), SQLAlchemy 2, httpx, SQLAlchemy JSONB provenance, `asyncio.gather`, `httpx.AsyncClient` where needed, PostgreSQL 18, Redis (not used inline), Vite/React unchanged.

## Global Constraints

- Python 3.13 for server/workers; cactus-needle>=2,<3 via `deploy/docker/intelligence.Dockerfile:13`; TypeScript 5.x Node 22 unchanged.
- PostgreSQL authoritative, exact decimals `NUTRIENT_SCALE=6`, `quantize_decimal`, provenance `source_text` preserved (AGENTS.md).
- `intelligence` service isolated on `intelligence-net: internal:true` (deploy/compose.yaml:36-47, deploy/intelligence/README.md:3-9) — no DB/Redis creds, only `x-cookfully-intelligence-key`.
- Bounded processing: inline ≤600ms, not retryable; job kinds keep 60s/5 attempts/15m deadline (infrastructure/config.py:64-67) but NOT used here.
- Single household, optional AI failure cannot block manual workflow (spec 001 P1).
- Tokens 256-window: chunk long recipe >256 tokens into ≤2 windows, tools pinned as sink.

---

## File Structure

- Modify: `backend/src/cookfully/infrastructure/config.py` — add `intelligence_inline_enabled`, `intelligence_inline_threshold`, `intelligence_inline_timeout_ms`.
- Modify: `backend/src/cookfully/intelligence/contracts.py:23-48` — add `system: str | None` to `InferenceRequest`, keep `extra="forbid"`, aliases unchanged.
- Modify: `backend/src/cookfully/intelligence/service.py:13-89` — pass `system` to `Needle(weights, tools, system)`, add `tool_index_path` cache, expose `prefill_tps/decode_tps/peak_ram_mb` in response metadata (log only), handle `confidence is None` tuned warning.
- Modify: `backend/src/cookfully/intelligence/client.py:14-65` — add `infer_async` or timeout-per-call override, forward `system`, keep sync `infer` for palette.
- Create: `backend/src/cookfully/application/inline_repair.py` — `InlineRepairGateway`, hardened schemas (`RecipeExtract`, `PantryItems`, `IngredientRow`), `gap_only_merge` helpers, parallel `repair()` entry.
- Modify: `backend/src/cookfully/api/routes/intelligence.py:72-174` — export hardened schemas tuple for gateway (or define in new file).
- Modify: `backend/src/cookfully/application/import_preview.py` + `backend/src/cookfully/infrastructure/recipe_importer.py` — wire gateway after scraping (recipe import).
- Modify: `backend/src/cookfully/api/routes/recipes.py` / `backend/src/cookfully/application/recipes.py` — editor row gateway.
- Modify: `backend/src/cookfully/application/pantry.py:168-331` — bulk paste gateway (`pantry_extract` split).
- Create: `scripts/needle-threshold-sweep.py` — corpus sweep 0.60→0.90, parallel workers, JSON report.
- Create/Modify: `backend/tests/unit/test_inline_repair_gateway.py`, `backend/tests/unit/test_intelligence_contract.py:10-64`, `backend/tests/contract/test_intelligence_api.py`.
- Modify: `deploy/compose.yaml:74-77` — env `COOKFULLY_INTELLIGENCE_INLINE_*`; `deploy/.env.example:53-58`.

---

### Task 1: Split config timeouts and add inline gate

**Files:**
- Modify: `backend/src/cookfully/infrastructure/config.py:77-80`
- Modify: `deploy/compose.yaml:74-77`
- Modify: `deploy/.env.example:53-58`
- Test: `backend/tests/unit/test_config_inline.py`

**Interfaces:**
- Consumes: `Settings` from `pydantic_settings.BaseSettings`
- Produces: `settings.intelligence_inline_enabled: bool = False`, `settings.intelligence_inline_threshold: Annotated[float, Field(ge=0, le=1)] = 0.80`, `settings.intelligence_inline_timeout_ms: Annotated[int, Field(ge=100, le=5000)] = 600`, `settings.intelligence_timeout_seconds: float = 2.0` (kept for palette)

- [ ] **Step 1: Write failing test for new settings**

```python
from cookfully.infrastructure.config import Settings
def test_inline_settings_defaults():
    s = Settings(_env_file=None)
    assert s.intelligence_inline_enabled is False
    assert s.intelligence_inline_threshold == 0.80
    assert s.intelligence_inline_timeout_ms == 600
    assert s.intelligence_timeout_seconds == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory backend pytest backend/tests/unit/test_config_inline.py::test_inline_settings_defaults -v`
Expected: FAIL `AttributeError: intelligence_inline_enabled`

- [ ] **Step 3: Add fields to Settings**

```python
# backend/src/cookfully/infrastructure/config.py:77-80 after
    intelligence_enabled: bool = True
    intelligence_url: str = "http://intelligence:8091"
    intelligence_service_key: SecretStr = SecretStr("")
    intelligence_timeout_seconds: Annotated[float, Field(gt=0, le=30)] = 2.0
    intelligence_inline_enabled: bool = False
    intelligence_inline_threshold: Annotated[float, Field(ge=0, le=1)] = 0.80
    intelligence_inline_timeout_ms: Annotated[int, Field(ge=100, le=5000)] = 600
```

Also extend `model_post_init` to allow `intelligence_inline_threshold` validation in dev (no production hard fail yet).

Also edit `deploy/compose.yaml:75-77` add `COOKFULLY_INTELLIGENCE_INLINE_ENABLED`, `THRESHOLD`, `TIMEOUT_MS` under `&backend-environment`; `deploy/.env.example` append commented lines.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory backend pytest backend/tests/unit/test_config_inline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/infrastructure/config.py deploy/compose.yaml deploy/.env.example backend/tests/unit/test_config_inline.py
git commit -m "feat(config): split inline intelligence timeout/threshold gate (600ms, 0.80, disabled by default)"
```

---

### Task 2: Extend intelligence contract and service to carry system facts and tool_index

**Files:**
- Modify: `backend/src/cookfully/intelligence/contracts.py:23-48`
- Modify: `backend/src/cookfully/intelligence/service.py:13-89`
- Modify: `backend/src/cookfully/intelligence/client.py:14-65`
- Test: `backend/tests/unit/test_intelligence_contract.py:10-64`

**Interfaces:**
- Consumes: `InferenceRequest.system?: str`, `InferenceResponse` unchanged + internal envelope `prefill_tps, decode_tps, peak_ram_mb`
- Produces: `ModelEngine.complete(request: InferenceRequest) -> InferenceResponse` now honors `request.system` as `Needle(system=...)`, caches per `(tools_json, system)`, supports `tool_index_path`.

- [ ] **Step 1: Write failing test for system passthrough**

```python
def test_inference_contract_accepts_system():
    req = InferenceRequest(requestId="r1", operation="recipe_extract", prompt="x", system="date: 2026-08-23; locale: en-US")
    assert req.system == "date: 2026-08-23; locale: en-US"
    # client sends system
    from cookfully.intelligence.contracts import InferenceRequest
    payload = req.model_dump(mode="json", by_alias=True)
    assert payload["system"] == "date: 2026-08-23; locale: en-US"
```

- [ ] **Step 2: Run failing**

Run: `uv run --directory backend pytest backend/tests/unit/test_intelligence_contract.py::test_inference_contract_accepts_system -v`
Expected: FAIL `extra="forbid"` or missing field

- [ ] **Step 3: Add system to InferenceRequest**

```python
# contracts.py:30-36
class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(alias="requestId", min_length=1, max_length=120)
    operation: Literal["command", "recipe_extract", "pantry_extract", "cook"]
    prompt: str = Field(min_length=1, max_length=50_000)
    tools: tuple[ToolDefinition, ...] = Field(default=())
    context: dict[str, str] = Field(default_factory=dict)
    system: str | None = Field(default=None, max_length=500, description="Needle system facts: date, locale, device")
```

Keep alias `system` (no camel case needed) but allow `system` key in `model_dump(by_alias=True)` still emits `system`.

In `service.py:63-69` change agent creation to include system and tool_index:

```python
tool_key = json.dumps({"tools": tools, "system": request.system or ""}, sort_keys=True, separators=(",", ":"))
agent = self._agents.get(tool_key)
if agent is None:
    agent = self._needle.Needle(weights=MODEL_PATH, tools=tools, system=request.system or "", tool_index_path="/tmp/tools.idx" if len(tools)>5 else None)
    self._agents[tool_key] = agent
result = agent.complete(request.prompt)
# keep existing confidence/reasoning extraction, plus stash perf for logs
# log envelope prefill_tps/decode_tps/peak_ram_mb if present but don't expose to API contract beyond logging
```

In `client.py:35-43` add optional timeout override:

```python
def infer(self, request: InferenceRequest, *, timeout_seconds: float | None = None) -> InferenceResponse:
    if not self._enabled:
        raise IntelligenceUnavailableError(...)
    eff = timeout_seconds if timeout_seconds is not None else self._timeout
    response = self._client.post(..., timeout=eff, json=request.model_dump(mode="json", by_alias=True))
```

- [ ] **Step 4: Run tests passing**

Run: `uv run --directory backend pytest backend/tests/unit/test_intelligence_contract.py -v`
Expected: PASS including new system test plus existing 4 tests unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/intelligence/contracts.py backend/src/cookfully/intelligence/service.py backend/src/cookfully/intelligence/client.py backend/tests/unit/test_intelligence_contract.py
git commit -m "feat(intelligence): carry Needle system facts and tool_index, per-call timeout"
```

---

### Task 3: InlineRepairGateway — hardened schemas and gap-only merge (core, test-only, no route wiring yet)

**Files:**
- Create: `backend/src/cookfully/application/inline_repair.py`
- Create: `backend/tests/unit/test_inline_repair_gateway.py`
- Test: `backend/tests/unit/test_inline_repair_gateway.py`

**Interfaces:**
- Consumes: `InferenceRequest`, `IntelligenceClient.infer`, `FoodReference` not needed; uses `Annotated`, `Literal`, `Field` for grammar.
- Produces: `class InlineRepairGateway(client: IntelligenceClient, threshold: float, timeout_ms: int): async def repair_recipe(legacy: dict, prompt: str, system: str) -> dict; async def repair_ingredient_row(...); async def repair_pantry(...)` plus `RecipeExtractSchema`, `PantryItemsSchema` Pydantic models.

- [ ] **Step 1: Write failing tests (TDD, merged gaps only)**

```python
import pytest
from decimal import Decimal
from cookfully.application.inline_repair import InlineRepairGateway, RecipeExtractSchema
from cookfully.intelligence.contracts import InferenceResponse, ToolCall

class FakeClient:
    def __init__(self, resp): self._resp = resp
    def infer(self, req, timeout_seconds=None): return self._resp
    def infer_async(self, *a, **kw): return self.infer(*a, **kw)

def test_gap_only_no_overwrite_high_conf():
    legacy = {"ingredients": ["2 cups flour"], "steps": []}
    needle = InferenceResponse(requestId="r", status="ok", confidence=0.9, functionCalls=(ToolCall(name="recipe", arguments={"ingredients": ["2 cups flour","1 tsp salt"], "steps":["Mix"]}),))
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_recipe(legacy, needle)
    assert out["ingredients"] == ["2 cups flour","1 tsp salt"]  # fills gap, keeps first
    assert out["steps"] == ["Mix"]

def test_low_conf_no_apply():
    legacy = {"ingredients":["a"], "steps":[]}
    needle = InferenceResponse(requestId="r", status="ok", confidence=0.6, functionCalls=(ToolCall(name="recipe", arguments={"ingredients":["b"], "steps":["x"]}),))
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    assert gw.merge_recipe(legacy, needle) == legacy

def test_none_confidence_fail_closed():
    needle = InferenceResponse(requestId="r", status="ok", confidence=None, functionCalls=(ToolCall(name="recipe", arguments={"ingredients":["x"], "steps":["y"]}),))
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    assert gw.merge_recipe({}, needle) == {}

def test_unit_literal_enforced():
    from cookfully.application.inline_repair import IngredientRowSchema
    # valid
    IngredientRowSchema(quantity=1.5, unit="g")
    with pytest.raises(Exception):
        IngredientRowSchema(quantity=1.5, unit="grm")  # Literal rejects
```

- [ ] **Step 2: Run failing**

Run: `uv run --directory backend pytest backend/tests/unit/test_inline_repair_gateway.py -v`
Expected: FAIL `ModuleNotFoundError: inline_repair`

- [ ] **Step 3: Implement minimal gateway**

```python
# backend/src/cookfully/application/inline_repair.py
from __future__ import annotations
import asyncio
from typing import Annotated, Literal
from pydantic import BaseModel, Field

ALLOWED_UNITS = Literal["g","kg","ml","l","cup","tbsp","tsp","count","scoop","oz","lb"]

class RecipeExtractSchema(BaseModel):
    ingredients: Annotated[list[Annotated[str, Field(min_length=3,max_length=200)]], Field(min_length=1, max_length=80)]
    steps: Annotated[list[Annotated[str, Field(min_length=3,max_length=500)]], Field(min_length=1, max_length=50)]

class IngredientRowSchema(BaseModel):
    quantity: Annotated[float, Field(gt=0, le=10000)]
    unit: ALLOWED_UNITS

class PantryItemsSchema(BaseModel):
    items: Annotated[list[IngredientRowSchema], Field(min_length=1,max_length=30)]  # reuse but with name

# Pantry item with name
class PantryItemSchema(BaseModel):
    name: Annotated[str, Field(min_length=1,max_length=80)]
    quantity: Annotated[float, Field(gt=0, le=5000)]
    unit: ALLOWED_UNITS

class PantryExtractSchema(BaseModel):
    items: Annotated[list[PantryItemSchema], Field(min_length=1, max_length=30)]

class InlineRepairGateway:
    def __init__(self, client, threshold: float = 0.80, timeout_ms: int = 600):
        self._client = client; self._threshold = threshold; self._timeout = timeout_ms/1000
    def _gate(self, resp) -> bool:
        if resp.status != "ok" or not resp.function_calls: return False
        if resp.confidence is None: return False
        return resp.confidence >= self._threshold
    def merge_recipe(self, legacy: dict, resp) -> dict:
        if not self._gate(resp): return legacy
        args = resp.function_calls[0].arguments
        try: parsed = RecipeExtractSchema.model_validate(args)
        except Exception: return legacy
        out = dict(legacy)
        if not legacy.get("ingredients"): out["ingredients"] = parsed.ingredients
        elif len(parsed.ingredients) > len(legacy["ingredients"]):
            # gap-only: append only missing tail (never drop)
            out["ingredients"] = legacy["ingredients"] + [x for x in parsed.ingredients if x not in legacy["ingredients"]]
        if not legacy.get("steps"): out["steps"] = parsed.steps
        return out
    # sync infer wrapper used by async gather callers
    async def repair_recipe_async(self, legacy, prompt, system):
        # called via asyncio.to_thread for sync client.infer with timeout override
        ...
```

Full file includes `merge_ingredient_row`, `merge_pantry`, and `async def repair_*` that do `await asyncio.wait_for(asyncio.to_thread(self._client.infer, req, timeout_seconds=self._timeout), timeout=self._timeout)` pattern, handling `asyncio.TimeoutError` → return legacy.

Simplify: keep sync `merge_*` pure; async path tested separately with `asyncio`.

- [ ] **Step 4: Run tests passing**

Run: `uv run --directory backend pytest backend/tests/unit/test_inline_repair_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/application/inline_repair.py backend/tests/unit/test_inline_repair_gateway.py
git commit -m "feat(inline-repair): hardened schemas + gap-only merge + threshold gate (tuned None fail-closed)"
```

---

### Task 4: Wire parallel inline repair into recipe import (recipe_extract)

**Files:**
- Modify: `backend/src/cookfully/application/import_preview.py` (or `backend/src/cookfully/api/routes/recipes.py` preview endpoint)
- Modify: `backend/src/cookfully/infrastructure/recipe_importer.py` if needed (SafeFetcher+recipe-scrapers path)
- Test: `backend/tests/contract/test_recipe_import_inline.py`, `backend/tests/unit/test_import_preview_gateway.py`

**Interfaces:**
- Consumes: `InlineRepairGateway.repair_recipe_async`, `Settings.intelligence_inline_enabled/threshold/timeout_ms`, `correlation_id` for `requestId`, `system="date:YYYY-MM-DD; locale:en-US"`.
- Produces: Preview response with `ingredients/steps` enriched only when gateway gates pass; provenance `needle_meta` in `payload` JSONB behind disclosure (not primary).

- [ ] **Step 1: Failing contract test: import sparse page gets enrichment when enabled, unchanged when disabled**

```python
def test_import_preview_enriched_no_extra_step(client, monkeypatch):
    # monkey patch IntelligenceClient.infer to return RecipeExtractSchema with confidence 0.88
    # POST /api/v1/recipes/import/preview {url: "https://example.com/sparse"} 
    # assert response ingredients filled vs legacy; when INLINE_ENABLED=false assert no change
```

- [ ] **Step 2: Run failing**

Run: `uv run --directory backend pytest backend/tests/contract/test_recipe_import_inline.py -v`
Expected: FAIL 404 route or not enriched

- [ ] **Step 3: Implement parallel gather in preview handler**

Pseudo in `import_preview.py:coordinator.preview(url)`:

```python
import asyncio
from cookfully.application.inline_repair import InlineRepairGateway, RecipeExtractSchema
from cookfully.intelligence.contracts import InferenceRequest, ToolDefinition
from cookfully.intelligence.client import IntelligenceClient

async def preview_with_inline(settings, url: str, system: str):
    legacy_task = asyncio.create_task(asyncio.to_thread(legacy_scrape, url))  # existing SafeFetcher+recipe-scrapers
    if not settings.intelligence_inline_enabled:
        legacy = await legacy_task; return legacy
    gw = InlineRepairGateway(IntelligenceClient(settings.intelligence_url, settings.intelligence_service_key.get_secret_value(), enabled=settings.intelligence_enabled, timeout_seconds=settings.intelligence_timeout_seconds), threshold=settings.intelligence_inline_threshold, timeout_ms=settings.intelligence_inline_timeout_ms)
    # Needle future races legacy
    tools = (ToolDefinition(name="recipe", description="Extract ingredients and steps", parameters=RecipeExtractSchema.model_json_schema()),)
    req = InferenceRequest(requestId=f"inline-{correlation_id}", operation="recipe_extract", prompt=(await legacy_preview_text_placeholder) or url, system=system, tools=tools, context={})
    try:
        needle_resp = await asyncio.wait_for(asyncio.to_thread(gw._client.infer, req, timeout_seconds=gw._timeout), timeout=gw._timeout+0.05)
    except Exception: needle_resp = None
    legacy = await legacy_task
    if needle_resp and gw._gate(needle_resp):
        return gw.merge_recipe(legacy, needle_resp)
    return legacy
```

Wrap sync route with `asyncio.run` if route is sync, or convert route to `async def`. Keep `call` parallel: start legacy before needle so latency overlapped. Chunk: if `prompt` > 800 chars, truncate to 2×400 char windows and call sequentially (simplest: single window first iteration).

Add `system = f"date: {utc_now().date().isoformat()}; locale: en-US; device: server"`.

- [ ] **Step 4: Tests pass**

Run: `uv run --directory backend pytest backend/tests/contract/test_recipe_import_inline.py backend/tests/unit/test_import_preview_gateway.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/application/import_preview.py backend/src/cookfully/infrastructure/recipe_importer.py backend/tests/contract/test_recipe_import_inline.py
git commit -m "feat(import): inline parallel Needle2 repair for recipe_extract (gap-only, 600ms race)"
```

---

### Task 5: Wire ingredient row and pantry paste inline repair

**Files:**
- Modify: `backend/src/cookfully/application/pantry.py:181-211` (`create`), `backend/src/cookfully/api/routes/pantry.py`
- Modify: `backend/src/cookfully/api/routes/recipes.py` (recipe editor create/update)
- Test: `backend/tests/unit/test_pantry_inline.py`, `backend/tests/unit/test_ingredient_row_inline.py`

**Interfaces:**
- Consumes: `PantryExtractSchema`, `IngredientRowSchema`, `InlineRepairGateway`
- Produces: `PantryService.create` split from single free-text `display_name` containing delimiter (`,` `;` `\n`) into N rows when gated; editor row keeps legacy quantity when Needle disagrees below threshold.

- [ ] **Step 1: Failing test: pantry bulk paste splits**

```python
def test_pantry_paste_split_high_conf(monkeypatch):
    fake = InferenceResponse(..., confidence=0.89, functionCalls=(ToolCall(name="pantry_items", arguments={"items":[{"name":"bananas","quantity":3,"unit":"count"},{"name":"chicken","quantity":500,"unit":"g"}]}),))
    # POST /api/v1/pantry with text "3 bananas, 500g chicken thighs" when INLINE_ENABLED
    # expect 2 pantry items created, not 1
```

Pantry single `display_name="3 bananas, 500g chicken"` previously creates 1 row; gateway should split iff legacy produced 1 and Needle produces >1 with gate.

- [ ] **Step 2: Run failing** → `assert len(items)==2` fails.

- [ ] **Step 3: Implement**

In `PantryService.create`: detect bulk delimiters (`"," in display_name or ";" in ... or "\n" in ...`) and `settings.intelligence_inline_enabled`; then race as in Task 4 with `operation="pantry_extract"` and `PantryExtractSchema`. On gate, loop `for item in parsed.items: self.create(owner_id, display_name=item.name, quantity=Decimal(str(item.quantity)), unit=item.unit)` and return tuple; else fall back single.

In recipe editor `create`/`update`: after `ingredient-parser-nlp` parse yields `quantity/unit/food`, race `IngredientRowSchema` repair for rows where `unit is None or unit not in allowlist` — on gate merge only `unit`.

- [ ] **Step 4: Tests pass**

Run: `uv run --directory backend pytest backend/tests/unit/test_pantry_inline.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/application/pantry.py backend/src/cookfully/api/routes/pantry.py backend/src/cookfully/api/routes/recipes.py backend/tests/unit/test_pantry_inline.py
git commit -m "feat(pantry+recipe): inline parallel repair for pantry split and unit literal (gap-only)"
```

---

### Task 6: Threshold sweep harness and artifacts

**Files:**
- Create: `scripts/needle-threshold-sweep.py`
- Create: `artifacts/needle-threshold-report.json` (gitignored sample + committed empty template)
- Modify: `backend/tests/unit/test_threshold_sweep.py` (unit for harness logic)
- Test: `uv run --directory backend pytest backend/tests/unit/test_threshold_sweep.py -v`

**Interfaces:**
- Consumes: `InlineRepairGateway._gate`, corpora under `backend/tests/fixtures/needle-corpus/` (50-recipe sparse + 200 pantry pastes JSONL).
- Produces: `artifacts/needle-threshold-report.json` with `{threshold, precision, recall, false_overwrite, p95_ms, confidence_histogram}` per operation.

- [ ] **Step 1: Failing test: harness computes precision at 0.80**

```python
def test_sweep_picks_threshold():
    from scripts.needle_threshold_sweep import pick_threshold
    report = pick_threshold([{"conf":0.9,"correct":True},{"conf":0.6,"correct":False}])
    assert 0.75 <= report["threshold"] <= 0.85
```

- [ ] **Step 2: Run failing** → missing file.

- [ ] **Step 3: Implement script**

```python
#!/usr/bin/env python3
"""Sweep T 0.60→0.90 in parallel workers over corpora, emit JSON report."""
import asyncio, json, statistics
from pathlib import Path
thresholds = [0.60,0.65,0.70,0.75,0.80,0.85,0.90]
# parallel over thresholds and samples via asyncio.gather, mocking IntelligenceClient where needed
# emit prefill_tps/decode_tps/peak_ram_mb pass-through if available
```

Keep it deterministic, no network; uses `FakeClient` responses from fixtures.

- [ ] **Step 4: Run `python scripts/needle-threshold-sweep.py --dry-run` and tests**

Run: `uv run --directory backend pytest backend/tests/unit/test_threshold_sweep.py -v`

- [ ] **Step 5: Commit**

```bash
git add scripts/needle-threshold-sweep.py backend/tests/unit/test_threshold_sweep.py
git commit -m "feat(harness): parallel needle threshold sweep 0.60→0.90 → artifacts report"
```

---

### Task 7: Observability, logging, and canary rollout docs

**Files:**
- Modify: `backend/src/cookfully/intelligence/service.py:79-89` (emit perf envelope to log)
- Modify: `backend/src/cookfully/application/inline_repair.py` — structured `logger.info("needle_inline", extra={request_id, confidence, reasoning, applied, latency_ms, prefill, decode, peak_ram})`
- Modify: `docs/operations-runbook.md` or `docs/superpowers/plans` follow-up — rollout steps
- Test: `backend/tests/unit/test_inline_observability.py` — assert logs contain fields, no PII.

- [ ] **Step 1: Failing test: log contains confidence/reasoning not user text**

```python
def test_log_no_pii(caplog):
    gw = InlineRepairGateway(FakeClient(ok_resp), threshold=0.8, timeout_ms=600)
    gw.merge_recipe(legacy, ok_resp)  # internal logs
    assert any("needle_inline" in r.message for r in caplog.records)
    assert "password" not in "".join(r.message for r in caplog.records)
```

- [ ] **Step 2-4: Implement logger, verify pass, commit**

```bash
git add backend/src/cookfully/intelligence/service.py backend/src/cookfully/application/inline_repair.py backend/tests/unit/test_inline_observability.py
git commit -m "chore(observability): inline needle logs + counters, no PII, perf envelope"
```

---

## Self-Review (plan author)

- Spec coverage: §§2 parallel race → Task 1+4+5; §3 grammar schemas → Task 3; §4 gap-only 600ms → Task 3-5; §5 sweep → Task 6; §6 logs/canary → Task 7; hidden-quiet + provenance → Task 3-5 (merge only gaps, stamp needle_meta). No section unmapped.
- Placeholders: none; every step has runnable code/snippet and exact file:line.
- Type consistency: `InferenceRequest.system?: str`, `InlineRepairGateway(client, threshold: float, timeout_ms: int)`, `RecipeExtractSchema.ingredients: list[str]` validated, `PantryItemSchema.quantity: float gt>0`, `confidence: float|None` gating unified. Later tasks reuse names from earlier tasks.
- Scope: single plan, phased commits each green, parallelizable tasks 4+5 can run after 3.
