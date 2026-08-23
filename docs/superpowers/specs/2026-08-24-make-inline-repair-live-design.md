# Make Inline Repair Live — Design

Date: 2026-08-24
Status: Approved (brainstormed 2026-08-24, Approach 1: Live with List+Tok+Canary)
Branch: `make-inline-live` (worktree `.worktrees/make-inline-live`)
Spec: This file | Plan to follow `docs/superpowers/plans/2026-08-24-make-inline-repair-live.md`
Related: `docs/superpowers/specs/2026-08-23-needle2-inline-repair-design.md` (Approach 2 gateway), `backend/src/cookfully/application/inline_repair.py:18-331`, `backend/src/cookfully/infrastructure/config.py:81-83`, `backend/src/cookfully/application/import_preview.py:72-257`, `backend/src/cookfully/api/routes/pantry.py:58-199`, `backend/src/cookfully/intelligence/service.py:68-80`, `deploy/compose.yaml:70-73`, `artifacts/needle-threshold-report.json:354-359` (chosen 0.75, p95 31ms)
Model: Needle2 `needle2.cact` 45M/14MB, 256-tok sliding window, grammar-constrained, confidence-calibrated

## Problem

Inline repair gateway is correct but **dormant**: `intelligence_inline_enabled=false` default (`infrastructure/config.py:81`) so prod sees zero effect; prompt windowing is char-truncate `raw[:800][:400][:256]` not `256-tok` (`import_preview.py:107-112`, `pantry.py:90-93`, dead `if len>800` after `[:256]`); bulk pantry creates `N` rows but `POST /pantry-items` returns only `created[0]` (`api/routes/pantry.py:139-166`) — client/replay thinks `1`; `tool_index_path` ephemeral `/tmp` (`service.py:79`); prod `compose.yaml` not `read_only`. Together they keep the feature at `7.8/10` not `9+`.

## Goal

Make `1+2+3` live together — still hidden-quiet, still `≤600ms` parallel gap-only `confidence≥T` (`T=0.80` default, report `0.75` available) — by fixing windowing, fixing bulk shape, flipping live default with canary, hardening persistence. No new endpoint, no new UI.

Non-goals: `command` palette old path (`frontend/src/app/CommandPalette.tsx:47`), `cook` echo (`api/routes/intelligence.py:424`), MCP, second-window beyond first retry, LoRA retune — next slice.

## Architecture

```
Fetcher HTML (50 KiB, 250 ms) ──┐
                                 ├─ race 600ms ─┐
Legacy scrape/parser (30-120 ms) ┘              ├─ gap-only merge ── DB (exact decimals)
Needle: _window(first 100-tok)→complete(system+OneSchema, 600ms)─┘       bulk: N rows → 201 [N]
                                                   second window only if [] + has_more + budget>120ms
```

Insertion points unchanged: `application/import_preview.py:preview()` races fetched HTML vs Needle `recipe_extract`; `api/routes/pantry.py:async create_pantry_item` bulk path now returns list; `api/routes/recipes.py:gather` unit rows. `intelligence` stays `internal:true` model-only.

## Components

* **`application/inline_repair.py`** — add `_window(prompt: str) -> tuple[str,bool]` (tok-aware) + `prompt_toks_est` logging; `ALLOWED_UNITS` Literal unchanged.
* **`infrastructure/config.py:81-83`** — `intelligence_inline_enabled` default `False → True`; keep `threshold 0.80`, `timeout 600`.
* **`api/routes/pantry.py:58-199`** — new `BulkPantryCreateResponse(items: list[PantryItemResponse], created: int)`; `POST /pantry-items` `response_model=PantryItemResponse|Bulk…` Union — single when `"," not in name` (compat), bulk list when gated.
* **`application/import_preview.py:107-112` + `api/routes/pantry.py:90-93`** — replace char slices with `_window`.
* **`intelligence/service.py:79`** — `tool_index_path` `/tmp/tools.idx` → hashed `/models/tools.idx` (on `intelligence-model-data`, `tmpfs /tmp`).
* **`deploy/compose.yaml:36-47,70-73`** — `intelligence` `read_only: true`, `tmpfs: ["/tmp"]`, `volumes: […:ro]`; prod override keeps `INLINE_ENABLED=false` canary until gate.

## Data flow

1. `GET` requestid `inline-{correlation_id}` (`infrastructure/observability.correlation_id`) `operation=recipe_extract|pantry_extract|command` `prompt=window` `system="date:YYYY-MM-DD; locale:en-US; device:server"` `tools=(OneSchema)` `context={}`.
2. `asyncio.wait_for(to_thread(client.infer, timeout_seconds=gw._timeout), timeout=gw._timeout)` (`:168`) `except (TimeoutError, asyncio.TimeoutError)` unify — no `+0.05` buffer.
3. `_gate` `status!="ok" or !function_calls or confidence is None or <T` → discard (`inline_repair.py:53-58`) fail-closed.
4. Gap-only merge: recipe `if !ingredients → parsed else tail-append by name not in legacy` (`:90-96`); `if !steps → parsed` (`:97`); pantry bulk `N>1` via `_create_single` loop ×N (`pantry.py:142-152` now returns list); ingredient unit only `if legacy_unit None or not in allowed → parsed` (`:118-121`), `quantity` never touched.
5. Emit `logger.info("needle_inline", extra={request_id, confidence, reasoning, applied, latency_ms, prefill, decode, peak_ram, prompt_toks_est, window_index})` — no user text.

## Tok window strategy

```python
def _window(prompt: str) -> tuple[str, bool]:
    # 1 tok ≈ 4 chars heuristic; try tiktoken if installed
    try:
        import tiktoken
        toks = len(tiktoken.get_encoding("cl100k_base").encode(prompt))
    except Exception:
        toks = len(prompt)//4
    if toks <= 100:
        return (prompt[:400] if len(prompt)>400 else prompt)[:256], False
    has_more = len(prompt) > 400
    first = prompt[:400][:256]
    return first, has_more

# callonce window1; if resp is [] (unsupported) and has_more and remaining_budget>120ms → retry window prompt[400:800][:256] once
```

`prompt_chars`+`prompt_toks_est`+`window_index` logged; `max 2×100-tok` stays `≤600ms` (`report p95 31ms`).

## Bulk pantry shape

```python
class BulkPantryCreateResponse(BaseModel):
    items: list[PantryItemResponse]
    created: int = Field(ge=1)

@router.post("/pantry-items", response_model=PantryItemResponse | BulkPantryCreateResponse, status_code=201)
async def create_pantry_item(... ) -> PantryItemResponse | BulkPantryCreateResponse:
    if not has_bulk: return single  # "," ";" "\n" not in display_name
    if not gate or len(parsed.items)<=1: return single
    created = [service._create_single(owner.id, display_name=i.name, quantity=Decimal(str(i.quantity)), unit=i.unit, expires_on=payload.expires_on, food_reference_id=None) for i in parsed.items]
    bulk = BulkPantryCreateResponse(items=[PantryItemResponse.from_read(r) for r in created], created=len(created))
    # idempotency stores vector bulk_{key}
    return bulk
```

Replay returns same vector (full list). Non-bulk single path unchanged → frontend `Array.isArray(resp.items) ? resp.items : [resp]`.

## Enablement & hardening

* `infrastructure/config.py:81` `intelligence_inline_enabled=False → True` default true for dev/test (live immediately where `needle2.cact` exists).
* `deploy/compose.yaml` prod keeps `COOKFULLY_INTELLIGENCE_INLINE_ENABLED=false` override until canary gate; one env `false` still killswitches (`import_preview:88`, `pantry:78`).
* `deploy/compose.yaml` intelligence: `read_only: true`, `tmpfs: ["/tmp"]`, `volumes: ["intelligence-model-data:/models:ro"]`.
* `intelligence/service.py:79` `tool_index_path="/tmp/tools.idx" if len>5 else None` → `"/models/tools.idx"` (hash-persisted, `/tmp` tmpfs).
* Threshold stays `0.80` (safe `precision 1.0 false_overwrite 0.0`); `0.75` available per `report.json:354` when recall needed.
* Runbook canary `5%→25→100` gated on `false_overwrite<1%` + real `prefill/decode` `p95<600ms` on hardware (synthetic `31ms` today).

## Error handling

* Timeout → legacy (`except (asyncio.TimeoutError, TimeoutError): return legacy` unified `I3`).
* `[]` / `confidence None` / `<T` / shape invalid → legacy fail-closed, `_emit_log(applied=False)`.
* No overwrite: `quantity` never written, `unit` only when gap/invalid, recipe tail-append only.
* Long prompts >800 chars truncated to first window; second window only on empty + budget.

## Testing

* Unit (existing + new): `test_window_toks_heuristic`, `test_window_second_retry_budget`, `test_pantry_bulk_returns_list`, `test_pantry_nonbulk_single`, `test_config_inline_enabled_default_true`, `test_log_prompt_toks_no_pii`.
* Contract: `POST /pantry-items` bulk returns `201 {items:[],created:N}`, single returns `PantryItemResponse`; `GET /health` unchanged.
* Existing 28 unit tests must stay pass; `ruff format --check .`, `ruff check .`, `mypy src` clean; `uv run --directory backend pytest` (bulk + window + observability).
* Manual: canary log `prompt_toks_est/window_index` no PII via `test_inline_observability` pattern.

## Phasing

This spec is single slice `1+2+3`; next slice is `command/cook` + real-model hardware `prefill/decode` proof, then MCP.
