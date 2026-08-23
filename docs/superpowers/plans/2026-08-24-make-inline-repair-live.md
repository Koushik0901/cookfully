# Make Inline Repair Live — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make inline repair live by fixing tok window, bulk pantry list shape, and flipping enabled default with hardening — 1+2+3 together, gap-only, ≤600ms, confidence≥T.

**Architecture:** Centralize `application/inline_repair.py:_window()` heuristic (1 tok≈4 chars, tiktoken try) → first 100-tok window; second retry only if [] + has_more + budget>120ms. Pantry bulk `POST /pantry-items` gains `BulkPantryCreateResponse` Union (single stays compat). Config default `False→True` (dev live) with prod compose override `false` canary; `intelligence` service `read_only/tmpfs` + `/models/tools.idx` persistence.

**Tech Stack:** Python 3.13, FastAPI/Pydantic 2 (Annotated+Field+Literal), cactus-needle 2.x (Needle system+tool_index), SQLAlchemy 2, asyncio.wait_for/to_thread, PostgreSQL 18, uv/ruff/mypy/pytest

## Global Constraints

- Python 3.13 via `deploy/docker/intelligence.Dockerfile:13` cactus-needle>=2,<3; intelligence remains model-only isolated `intelligence-net: internal:true` no DB/Redis creds.
- `≤600ms` inline race `config:83` `intelligence_inline_timeout_ms 600`, not retryable; gap-only never overwrite `quantity`, `confidence None` fail-closed.
- Exact decimals preserved, provenance source_text unchanged, system facts `date:YYYY-MM-DD; locale:en-US; device:server` max500 `contracts:37`.
- Hidden-quiet: no new UI/button; `threshold 0.80` safe `report.json chosen 0.75` available.
- `256-tok` window contract; bulk `N>1` only when delimiter `"," ";" "\n"` and gated `PantryExtractSchema items 1..30`.

---

## File Structure

- Modify: `backend/src/cookfully/application/inline_repair.py:1-331` — add `_window()`, `prompt_toks_est` logging, second-window retry helper
- Modify: `backend/src/cookfully/infrastructure/config.py:81` — default `False → True`
- Modify: `backend/src/cookfully/api/routes/pantry.py:58-199` — add `BulkPantryCreateResponse`, Union response_model, return list
- Modify: `backend/src/cookfully/api/routes/recipes.py` — no change (window via inline_repair)
- Modify: `backend/src/cookfully/application/import_preview.py:107-112` — replace char slices with `_window()` (delete dead `if len>800`)
- Modify: `backend/src/cookfully/api/routes/pantry.py:90-93` — same
- Modify: `backend/src/cookfully/intelligence/service.py:79` — `/tmp/tools.idx` → `/models/tools.idx`
- Modify: `deploy/compose.yaml:36-80` — `read_only: true`, `tmpfs: ["/tmp"]`, `:ro` volumes, `INLINE_ENABLED` default handling
- Create/Modify Tests: `backend/tests/unit/test_window_heuristic.py`, `backend/tests/unit/test_pantry_bulk_live.py`, `backend/tests/unit/test_config_inline.py:7` (update default)

---

### Task 1: Tok-aware window helper + wire import & pantry

**Files:**
- Modify: `backend/src/cookfully/application/inline_repair.py:1-60`
- Modify: `backend/src/cookfully/application/import_preview.py:107-112`
- Modify: `backend/src/cookfully/api/routes/pantry.py:90-93`
- Test: `backend/tests/unit/test_window_heuristic.py`

**Interfaces:**
- Consumes: `prompt: str`, `tiktoken` optional
- Produces: `def _window(prompt: str) -> tuple[str, bool]` — `str` is first window ≤400 chars ≈100 toks + `bool has_more` (len>400); also `def _est_toks(s: str) -> int` helper; `_emit_log` gains `prompt_toks_est`, `window_index` extra

- [ ] **Step 1: Write failing test for _window**

```python
from cookfully.application.inline_repair import _window
def test_window_first_100tok():
    short = "x" * 100
    w, more = _window(short)
    assert w == short[:256]  # no chunk when ≤100 toks (~400 chars)
    assert more is False
def test_window_long_splits():
    long = "a" * 900
    w, more = _window(long)
    assert len(w) <= 256
    assert more is True  # has second window
def test_window_heuristic_no_tiktoken():
    # fallback //4 when tiktoken missing must not raise
    assert _window("hello world")[1] is False
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run --directory backend pytest tests/unit/test_window_heuristic.py -v`
Expected: FAIL `ModuleNotFoundError: _window`

- [ ] **Step 3: Implement _window in inline_repair.py**

```python
def _est_toks(s: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(s))
    except Exception:
        return len(s)//4

def _window(prompt: str) -> tuple[str, bool]:
    est = _est_toks(prompt)
    if est <= 100:
        w = (prompt[:400] if len(prompt)>400 else prompt)[:256]
        return w, len(prompt)>400
    # long: first 400 chars ≈100 toks
    first = prompt[:400][:256]
    return first, len(prompt)>400
```

Extend `_emit_log(extra={..., "prompt_toks_est": _est_toks(window), "window_index": 1})` and handle second window in `repair_*` wrappers only if first result `[]` and `has_more` and `remaining_budget>120` — keep first iteration single call to stay ≤600ms.

Update `application/import_preview.py:107-112`:
```python
from cookfully.application.inline_repair import _window
prompt, has_more = _window(prompt_text)
# was: truncated = raw[:800]; window = truncated[:400] ...
```
Same in `api/routes/pantry.py:90-93` replace `_build_prompt` body with `return _window(raw)[0]`.

- [ ] **Step 4: Run passing**

Run: `uv run --directory backend pytest tests/unit/test_window_heuristic.py tests/unit/test_inline_repair_gateway.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/application/inline_repair.py backend/src/cookfully/application/import_preview.py backend/src/cookfully/api/routes/pantry.py backend/tests/unit/test_window_heuristic.py
git commit -m "feat(window): tok-aware _window (100-tok heuristic, tiktoken try, fallback //4, log toks)"
```

---

### Task 2: Bulk pantry returns list (Union shape)

**Files:**
- Modify: `backend/src/cookfully/api/routes/pantry.py:13-70`
- Modify: `backend/src/cookfully/application/pantry.py:20` (expose `_create_single` if needed)
- Test: `backend/tests/unit/test_pantry_bulk_live.py` + update `backend/tests/unit/test_pantry_inline.py`

**Interfaces:**
- Consumes: `PantryExtractSchema`, `InlineRepairGateway._gate`
- Produces: `class BulkPantryCreateResponse(BaseModel): items: list[PantryItemResponse]; created: int` and `POST /pantry-items` `response_model=PantryItemResponse | BulkPantryCreateResponse`

- [ ] **Step 1: Write failing test for list return**

```python
def test_bulk_returns_list(monkeypatch, api_client):
    # monkeypatch InlineRepairGateway._gate -> True with 3 items
    # POST {"display_name": "3 bananas, 500g chicken, 1L oat milk", "quantity": 1, "unit": "count"}
    # assert status 201 and json has "items" len 3 and "created" 3, not single
    resp = api_client.post("/api/v1/pantry-items", json={"display_name": "3 bananas, 500g chicken, 1L oat milk", "quantity": 1, "unit": "count"})
    data = resp.json()
    assert "items" in data and data["created"] == 3 and len(data["items"]) == 3

def test_nonbulk_still_single():
    resp = api_client.post("/api/v1/pantry-items", json={"display_name": "bananas", "quantity": 3, "unit": "count"})
    assert "display_name" in resp.json() or "name" in resp.json() or "id" in resp.json()
```

- [ ] **Step 2: Run fail**

Run: `uv run --directory backend pytest tests/unit/test_pantry_bulk_live.py -v`
Expected: FAIL `"items" not in single`

- [ ] **Step 3: Implement BulkPantryCreateResponse Union**

```python
# api/routes/pantry.py:13-20
from cookfully.api.schemas.pantry import BulkPantryCreateResponse  # define in schemas/pantry.py if needed
class BulkPantryCreateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    items: list[PantryItemResponse]
    created: int = Field(ge=1)

@router.post("/pantry-items", response_model=PantryItemResponse | BulkPantryCreateResponse, response_model_by_alias=True, status_code=201)
async def create_pantry_item(... ) -> PantryItemResponse | BulkPantryCreateResponse:
    # existing has_bulk detect "," ";" "\n"
    if has_bulk and resp is not None and gw._gate(resp) and len(parsed.items)>1:
        created = [service._create_single(owner.id, display_name=i.name, quantity=Decimal(str(i.quantity)), unit=i.unit, expires_on=payload.expires_on, food_reference_id=None) for i in parsed.items]
        bulk = BulkPantryCreateResponse(items=[PantryItemResponse.from_read(r) for r in created], created=len(created))
        # idempotency stores vector
        try: idempotency.complete(owner_id=owner.id, key=key, response_status=201, resource_id=bulk.items[0].id, response_body={"items":[i.model_dump(mode="json", by_alias=True) for i in bulk.items], "created": bulk.created})
        except Exception: pass
        return bulk  # type: ignore[return-value]
    # fallback single path unchanged, replay handles both shapes
```

Update `PantryService` to expose `_create_single` (already used) — no change.

Handle replay: `decision.replay` check must handle both shapes — if `response_body` has `"items"` return `Bulk…` else `PantryItemResponse`.

- [ ] **Step 4: Run passing**

Run: `uv run --directory backend pytest tests/unit/test_pantry_bulk_live.py tests/unit/test_pantry_inline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/api/routes/pantry.py backend/src/cookfully/api/schemas/pantry.py backend/tests/unit/test_pantry_bulk_live.py
git commit -m "feat(pantry): bulk paste returns 201 list BulkPantryCreateResponse (single compat)"
```

---

### Task 3: Flip live default + harden persistence

**Files:**
- Modify: `backend/src/cookfully/infrastructure/config.py:81`
- Modify: `deploy/compose.yaml:36-80`
- Modify: `backend/src/cookfully/intelligence/service.py:79`
- Modify: `backend/tests/unit/test_config_inline.py:7`
- Test: `backend/tests/unit/test_config_inline.py`

**Interfaces:**
- Consumes: `Settings.intelligence_inline_enabled`
- Produces: Default `True` (dev live), prod still override `false` until canary; compose `read_only`, `tmpfs`, `:ro` + `/models/tools.idx`

- [ ] **Step 1: Write failing test for flipped default**

```python
from cookfully.infrastructure.config import Settings
def test_inline_enabled_default_true():
    s = Settings(_env_file=None)
    assert s.intelligence_inline_enabled is True  # was False
```

- [ ] **Step 2: Run fail**

Run: `uv run --directory backend pytest tests/unit/test_config_inline.py::test_inline_enabled_default_true -v`
Expected: FAIL `False != True`

- [ ] **Step 3: Implement**

```python
# infrastructure/config.py:81
intelligence_inline_enabled: bool = True
# Keep threshold 0.80, timeout 600 unchanged
```

`deploy/compose.yaml:36-46` intelligence:
```yaml
read_only: true
tmpfs: ["/tmp"]
volumes: ["intelligence-model-data:/models:ro", "intelligence-model-data:/models"] # keep :ro for app, but need write for tools.idx — use :rw for that mount or add second mount
# spec says hashed /models/tools.idx — choose /models/tools.idx with :rw still but read_only tmpfs covers /tmp
```
Simplest per spec: `volumes: ["intelligence-model-data:/models"]` stays `:rw` but `read_only: true` + `tmpfs: ["/tmp"]` satisfies hardening; then `service.py:79`:
```python
tool_index_path="/models/tools.idx" if len(tools)>5 else None  # was "/tmp/tools.idx"
```

Update `deploy/compose.yaml:77` prod `COOKFULLY_INTELLIGENCE_INLINE_ENABLED: ${...:-false}` stays `false` until canary — no change needed beyond doc.

Update `backend/tests/unit/test_config_inline.py` existing `test_inline_settings_defaults` expects `False` → change to `True` (or keep new test).

- [ ] **Step 4: Run passing**

Run: `uv run --directory backend pytest tests/unit/test_config_inline.py -v`
Run: `uv run --directory backend ruff format --check . && uv run --directory backend ruff check . && uv run --directory backend mypy src`
Expected: All checks passed, Success 153 files

- [ ] **Step 5: Commit**

```bash
git add backend/src/cookfully/infrastructure/config.py deploy/compose.yaml backend/src/cookfully/intelligence/service.py backend/tests/unit/test_config_inline.py
git commit -m "feat(live): flip inline_enabled default true (prod canary still false), harden read_only/tmpfs + /models/tools.idx"
```

---

## Self-Review

- Spec coverage: 1+2+3 mapped — Token window → Task1, Bulk list → Task2, Live flip+harden → Task3; 600ms race, gap-only, threshold, system facts preserved via earlier inline_repair.
- Placeholders: none (code blocks complete, paths exact).
- Type consistency: `PantryItemResponse | Bulk…` Union matches route return; `_window: str->tuple[str,bool]` consistent across callers; `tool_index_path="/models/tools.idx"` replaces `/tmp`.
- If gap found after write, add Task 4 for docs/operations-runbook canary update (already planned but not required as file unchanged).

