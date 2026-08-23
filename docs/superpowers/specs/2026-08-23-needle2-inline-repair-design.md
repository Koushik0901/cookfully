# Needle2 Inline Repair Gateway — Design

Date: 2026-08-23
Status: Approved (brainstormed 2026-08-23, Approach 2: Inline Repair Gateway, parallel-first)
Branch: `needle2-inline-repair` (worktree `.worktrees/needle2-inline-repair`)
Related: `backend/src/cookfully/intelligence/service.py`, `backend/src/cookfully/api/routes/intelligence.py`, `backend/src/cookfully/infrastructure/config.py`, `backend/src/cookfully/jobs/tasks.py`, `deploy/compose.yaml`, `specs/001-nutrition-recipe-planner/plan.md` (P1 accuracy gate, bounded processing), `DESIGN.md`, `AGENTS.md`
Model: Needle2 — 45M / 14 MB `needle2.cact` / ~28 MB RAM, 256-token sliding window, grammar-constrained tool calling = extraction, confidence-calibrated head (see `doc/apis.md`)

## Problem

Needle2 is deployed as a correct isolated service (`deploy/docker/intelligence.Dockerfile`, `deploy/compose.yaml:36-47` `intelligence-net: internal:true`, `service.py:40-89` model-only, no DB/Redis creds) but only ~25% of its designed capability is user-reachable: `CommandPalette` `createDraft("command")` (`frontend/src/app/CommandPalette.tsx:47`) while `recipe_extract` / `pantry_extract` / `cook` tools (`api/routes/intelligence.py:72-174`) and the async `POST /intelligence/extraction-jobs` path (`:296-334`, `jobs/tasks.py:28-175`) are server-ready and dead from UX. The product wants Needle2 to stay **hidden and quiet** — no extra button — but silently make every capture better, with an experimentally chosen confidence threshold (Option A: conservative auto-apply, threshold via tests). Approach 2 was selected over background-job enrichment (A1) and LoRA fine-tuning (A3) to keep the fix on the critical path but invisible.

## Goal

Invisible repair: on every existing capture path, try Needle2 in parallel with the legacy parser/scraper for ≤600 ms, and if `confidence ≥ T` and grammar-valid, fill **only gaps** (missing ingredients/steps, split pantry lines, unit typo → allowlist) without overwriting user text. Below threshold / timeout / `[]` → keep legacy untouched. Threshold `T` is chosen by a corpus harness sweeping `0.60→0.90`.

Non-goals: no new UI surface, no chat, no overwriting, no fine-tuned `.cact` this iteration (tuned weights report `confidence=None` per `needle/__init__.py:10-12` and break threshold gating).

## Architecture

```
Browser paste / import URL / editor row / pantry paste
  → API route (recipes/import, recipes create/update, pantry create)
    → parallel (asyncio.gather, 600ms budget):
        A) legacy: SafeFetcher → recipe-scrapers / ingredient-parser-nlp / Pint / food_matching (authoritative ~30-120ms)
        B) needle: IntelligenceClient.infer(
             InferenceRequest{ operation, prompt(truncated→256Tok), context→system, tools=[hardened schemas], system="date:YYYY-MM-DD; locale:en-US; device:…" },
             max_new_tokens=128, timeout=0.6s )
    → gap-only merge gated by confidence ≥ T + grammar shape
    → DB (Postgres authoritative, exact decimals, provenance preserved) → response
```

* Insertion points (application layer, not transport):
  * **Recipe import** — `ImportPreviewCoordinator` / `RecipeImporter` after `SafeFetcher+recipe-scrapers` sparse result → `recipe` single-tool extraction.
  * **Recipe editor ingredient row** — quantity/unit/food parse → unit `Literal` repair.
  * **Pantry** — `PantryService.create` bulk paste `"3 bananas, 500g chicken"` → `pantry_items` extraction → split rows.
* Shared `application/inline_repair.py` (`InlineRepairGateway`) reuses `IntelligenceClient` with **dual timeouts**: `intelligence_inline_timeout_ms=600` for gateway, `intelligence_timeout_seconds=2.0` kept for `CommandPalette` `command`. Reuses `ModelEngine` agent cache (`service.py:64-68`) keyed by `json.dumps(tools)` plus `tool_index_path="tools.idx"` when merged catalog >5, and injects `system` facts.
* Isolation unchanged: `intelligence` service stays model-only; API forwards only `prompt+tools+system` (no creds/IDs), `x-cookfully-intelligence-key` header (`client.py:41`).

## Tool schemas & grammar constraints

Needle2 guarantee: byte-level grammar compiled from schemas — only legal tokens scored, invalid keys/values unemittable (`doc/apis.md` Field, `needle/__init__.py`). All descriptions via Google-style `Args:` blocks.

| Domain | Legacy loose | Hardened inline schema | Needle pattern |
|---|---|---|---|
| `recipe_extract` | `ingredients: string[]`, `steps: string[]` | `ingredients: Annotated[list[str], Field(min_items=1,max_items=80)]` each `Field(min_length=3,max_length=200)`; `steps: Annotated[list[str], Field(min_items=1,max_items=50)]` | Single-tool extraction = `needle.extract(text, RecipeSchema)` equivalent; one declared tool → grammar admits exactly one call. |
| ingredient row | `quantity: number`, `unit: string` | `quantity: Annotated[float, Field(gt=0, le=10000)]`, `unit: Literal["g","kg","ml","l","cup","tbsp","tsp","count","scoop",…]` | Typo `grm→g` structurally forced via `Literal`. |
| `pantry_extract` | `items[]{name,quantity,unit}` loose | `name: Annotated[str, Field(min_length=1,max_length=80)]`, `quantity: Field(gt=0, le=5000)`, `unit: Literal[…]` | Split pastes without guessing units. |

Retrieval: if merged catalog >5, `Needle(tools, tool_index_path="tools.idx")` → top-5 per turn, embeddings persisted by fingerprint.
`reasoning` remains unconstrained (short span derivation `'ten minutes' -> minutes 10`); JSON stays constrained.

## Request/response flow & parallel gating

```
t0  gather(A legacy future, B needle future)
t0+600ms  select:
  if B == {type:"call", function_calls:[…], confidence>=T}
     and shape validates against Pydantic hardened model
     and provenance check (only fills null/empty gaps)
  → apply gap-only, stamp needle_meta={model:"needle2", confidence, reasoning, applied:true} (observability, collapsed behind disclosure)
  else (timeout | [] unsupported | confidence<T | confidence is None | shape invalid)
  → discard B, persist A unchanged
```

Invariants: `IdempotencyService` key per import URL hash / pantry paste hash (`IdempotencyService.request_hash` pattern `api/routes/intelligence.py:324`); no retries inline (unlike job `5 attempts/15m` `config.py:64-67`); long recipes chunked to 1–2 × 256-token windows (tools pinned as KV sink per Needle 256-window); inline respects `p95 reads <500ms` (`specs/001-nutrition-recipe-planner/plan.md:30`) by capping at 600ms and racing.

Confidence: `confidence = min(calibrated_head, decodeProb)` (`doc/apis.md#confidence`); `confidence is None` on tuned `.cact` → fail-closed (skip) this iteration.

## Threshold experiment harness

**Goal:** pick `T` that maximizes recall of gap-fills while keeping false-overwrite <1%.

* **Corpora (parallelized):** `50-recipe import failure set` (stable benchmark subset `plan.md:118` + 20 recent scraper-sparse pages; truth = `ingredients/steps`) + `200 pantry pastes` (synthetic + sampled receipts).
* **Runner:** `scripts/needle-threshold-sweep.py` — no DB writes; for `T in [0.60,0.65,…,0.90]` in parallel (asyncio ×8 workers), run Legacy vs Needle side-by-side per sample (same 600ms branch as gateway), record `confidence, reasoning, shape_valid, gap_filled, overwritten, latency (prefill_tps/decode_tps/peak_ram_mb)` from envelope `service.py:79-81` / `doc/apis.md` `prefill_tps/decode_tps/peak_ram_mb`.
* **Metrics:** `precision = applied & correct / applied`, `recall = gaps correctly filled / total gaps`, `false_overwrite`, `p95 latency`; output `artifacts/needle-threshold-report.json` + histogram `confidence vs correctness`.
* **Config:** `Settings` `intelligence_inline_threshold: float = 0.80` (`0–1`), `intelligence_inline_enabled: bool = True`, env `COOKFULLY_INTELLIGENCE_INLINE_THRESHOLD` hot-reloadable; kill-switch bypass without redeploy.
* **Gate:** 10-recipe smoke must pass at chosen `T` before 5% canary → 25→100% rollout; report committed for audit.

## Observability, safety & rollout

* **Signals (no user-facing banner):** `requestId=f"inline-{correlation_id}"` pattern (`api/main.py:61` `correlation_middleware`), `confidence, reasoning, p95, prefill/decode_tps, peak_ram_mb` → structured log + `histogram needle_inline_confidence` + `counter needle_inline_applied|skipped_timeout|skipped_lowconf|skipped_invalid`. `GET /intelligence/health` stays `ready/degraded` (`service.py:107-115`); `GET /api/v1/health` unchanged.
* **Fail-closed rails:** timeout >600ms, `[]` unsupported, `confidence is None`, grammar invalid → keep legacy; never overwrite non-empty user text; enforce `quantity>0`, `unit∈Literal` via grammar (unemittable); preserve exact-decimal and provenance contracts (`AGENTS.md`). `IdempotencyService` per draft prevents double-apply.
* **Material:** `intelligence_inline_timeout_ms` bounds apply; legacy path always wins on error; rollback is no-op (no overwrite).
* **Rollout:** ship `inline_enabled=false` default → night 1 sweep picks `T` → canary 5% imports → check false-overwrite <1% + p95 <600ms (parallel) → 25→100%; any breach → bump `T` +1 step. `intelligence_enabled=true` default unchanged (`config.py:77`) but fresh volumes still `model_artifact_missing → unavailable` fallthrough until operator places `needle2.cact` (`deploy/intelligence/README.md:11`).

## Phasing

Each phase independently shippable, tests green:

* **P1 — Gateway skeleton + import repair:** `application/inline_repair.py`, split timeouts (`infrastructure/config.py`), system-fact forwarding (`intelligence/client.py:41-42` + `service.py:69` extended to accept `system`), hardened `recipe` schema, `ImportPreviewCoordinator` integration, unit + contract tests (`test_intelligence_contract.py` style), sweep script + first report.
* **P2 — Ingredient row + pantry split:** hardened `unit`/`pantry_items` schemas, editor/pantry integration, `tool_index_path` caching, extended sweep.
* **P3 — Polish & promote:** canary → 100%, `docs/inspiration-review.md` entry, remove sweep scaffolding, fine-tune evaluation with collected failure labels (deferred `A3`).

## Testing

* Unit: `test_inline_repair_gateway.py` — budget timeout, confidence gating, `None` fail-closed, gap-only (no overwrite), chunked 256-window, parallel `gather` cancellation, `Literal` enforcement.
* Contract: `/api/v1/health` unchanged, `InferenceRequest` alias `requestId`/`functionCalls` preserved (`test_intelligence_contract.py:10-18`), operation enum still 4.
* Integration: import with sparse scraper → enriched; pantry paste split; editor row repair; idempotency replay.
* Performance: p95 read <500ms with inline enabled (100 measured ×3 runs per `plan.md:31`); `peak_ram_mb` ~28MB bound per session.
* AGENTS.md gates: `uv run --directory backend ruff format --check .`, `ruff check .`, `mypy src`, `pytest`, `pnpm --dir frontend typecheck` (no frontend change expected), Playwright not blocking hidden path.

## Rejected alternatives

* **A1 Background enrichment / A3 LoRA** — deferred: A1 adds job kind/lifecycle and UI polling; good after inline threshold is known. A3 loses calibrated confidence and needs 300–500 labeled samples per domain; best as follow-up with collected failures.

## Risks & mitigations

* 256-token window eviction on long recipes → chunk + pin tools as sink; empirical check via `prefill_tps` envelope.
* 600ms too tight under load → bounded `max_new_tokens=128` + agent cache + retrieval top-5 + fast `SDOT/NEON/AVX2` kernels per Needle co-design; if still tight, sweep will raise `T` or budget in data, not guess.
