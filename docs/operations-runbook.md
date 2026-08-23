# Operations Runbook

## Health, correlation, and safe diagnostics

`GET /api/v1/health` must be healthy before traffic is admitted. Every HTTP response carries
`X-Request-ID`; a valid incoming request ID is preserved, otherwise the server creates a UUIDv7.
Search logs by this value and job `traceId`. Structured logging recursively redacts passwords,
secrets, tokens, authorization/cookie values, prompts, goals, raw payloads, and HTML. Never paste
database URLs, cookie headers, bearer tokens, diagnostic files, or private nutrition goals into an
issue.

Failed-import HTML is off by default. When explicitly enabled it is encrypted at rest and expires
after 24 hours. Successful-import HTML and raw provider requests/responses are never retained.
Terminal job messages and task identifiers are reduced after 30 days; safe status, failure code, and
timestamps are deleted after one year. Run the retention sweep/reconciler on a schedule shorter than
the 24-hour diagnostic boundary and alert on failures.

## Durable job lifecycle

PostgreSQL is authoritative for jobs and outbox events; Redis only delivers work and coordinates
short-lived activity. API acknowledgement persists the aggregate, job, and outbox event and must
return in under one second. The outbox dispatcher publishes unsent events. Workers reject a stale
input hash before writing results, and handlers are idempotent.

Fixed timing policy:

| Control | Value |
| --- | --- |
| Visible job polling | 2 seconds |
| Other active-screen polling | 15 seconds |
| Attempt hard limit | 60 seconds (55-second soft limit) |
| Retry waits | 5s, 30s, 2m, 5m |
| Maximum attempts | 5 |
| Initial acceptance to terminal deadline | 15 minutes |
| Detailed diagnostic retention | 30 days |
| Safe job metadata retention | 1 year |

Retry only transient `dns_failed`, `source_unavailable`, and `network_timeout` failures. Invalid
content, blocked URLs/types/sizes, invalid structured provider output, stale inputs, and validation
errors require correction or manual continuation. `worker_stalled` is set when a running job misses
the 60-second heartbeat window; `deadline_exceeded` is terminal. The UI must announce queued,
running, retry-wait, partial, failed, superseded, and recovered states and must resume authoritative
polling after reload.

## Queue, broker, database, and provider recovery

- Redis unavailable: keep PostgreSQL and API up if health policy permits reads/manual writes. Restore
  Redis, run the outbox dispatcher/reconciler, and verify queued records are republished once.
- Worker unavailable: accepted jobs remain queued. Restart the worker, run stalled/deadline
  reconciliation, and verify input hashes before retrying.
- Outbox unavailable: no accepted work is lost. Restart it and compare unpublished event count before
  and after dispatch.
- PostgreSQL unavailable: stop writes and workers. Restore database health first; do not infer job
  completion from Redis messages.
- Provider disabled, timeout, invalid output, or failure: preserve manual recipe editing and manual
  nutrition corrections. Goals, plans, groceries, backup, and export remain usable. Surface partial or
  failed provenance rather than substituting invented nutrition.

After recovery, inspect the job plus aggregate by correlation ID, confirm exactly one authoritative
result, no stale write, and no secret-bearing diagnostic. Do not directly mark rows succeeded.

## Backup, restore, and upgrades

Run daily verified PostgreSQL/media backups and a restore drill at least quarterly. The independent
erasure-ledger volume is replicated separately and is never overwritten by restore. Follow
`docs/backup-restore.md`; a missing, behind, or discontinuous ledger is a hard activation failure.

Before upgrade: create and verify a backup, capture the current ledger head, read release notes, stop
web/API/worker/outbox/retention, apply migrations once, restart PostgreSQL/Redis dependencies, then API,
outbox/worker/retention, and web. Verify health, migration head, a manual read, a queued job, media
access, and the retention heartbeat.
Rollback application images only when the schema remains compatible; otherwise restore into a clean
target and prove ledger replay.

## Needle2 inline repair canary rollout (hidden, gap-only, 600ms)

Inline repair is disabled by default (`COOKFULLY_INTELLIGENCE_INLINE_ENABLED=false`). No UI change; threshold `T`
(`COOKFULLY_INTELLIGENCE_INLINE_THRESHOLD`, default `0.80`) and timeout `600ms` (`COOKFULLY_INTELLIGENCE_INLINE_TIMEOUT_MS`)
are hot-reloadable via env without redeploy. Kill-switch: set `INLINE_ENABLED=false` and restart API.

**Observability (no PII):**
- `logger="cookfully.intelligence"` emits `needle_infer` with `extra={request_id, confidence, reasoning, prefill, decode, peak_ram, latency_ms}`.
- `logger="cookfully.inline_repair"` emits `needle_inline` with `extra={request_id, confidence, reasoning, applied, latency_ms, prefill, decode, peak_ram}`.
- Never log prompt, ingredients, steps, or user text. Search by `request_id`/`X-Request-ID`.
- Counters derived from logs: `needle_inline_applied`, `skipped_timeout`, `skipped_lowconf`, `skipped_invalid` (applied=false + gate reason). Histogram `needle_inline_confidence`. Perf envelope `prefill_tps/decode_tps/peak_ram_mb` pass-through for p95 latency.

**Rollout steps:**

1. Night 0 — ship with `INLINE_ENABLED=false`. Place `needle2.cact` at `/models/needle2.cact` (`deploy/intelligence/README.md:11`) or service stays `unavailable` and falls through to legacy; verify `GET /intelligence/health` and `GET /api/v1/health` unchanged.
2. Night 1 — run sweep `python scripts/needle-threshold-sweep.py` (or `scripts/needle_threshold_sweep.py`) over corpora `backend/tests/fixtures/needle-corpus/*.jsonl` sweeping `0.60→0.90` in parallel; commit `artifacts/needle-threshold-report.json`. Choose `T` where `false_overwrite <1%` and `p95 <600ms` (parallel) and smoke `10-recipe` set passes.
3. Canary 5% — set `COOKFULLY_INTELLIGENCE_INLINE_ENABLED=true` and route 5% of imports/pantry bulk pastes (or feature-flag 5% of households) through gateway. Monitor for 24h: `false_overwrite <1%`, `p95 latency <600ms`, `peak_ram_mb ~28MB`, no increase in `skipped_invalid`. Logs must contain `confidence/reasoning` not user text.
4. 25% — if 5% passes, expand to 25% traffic. Check `needle_inline_applied` rate vs report; if breach (`false_overwrite ≥1%` or `p95 ≥600ms` or `decode_tps` drop), bump `T` +0.05 or revert to `INLINE_ENABLED=false` (rollback is no-op; no overwrite).
5. 100% — promote to 100% after 25% passes 24h. Keep threshold as single source (`config.intelligence_inline_threshold`). Any breach after 100% → raise `T` one step or disable inline; do not retry inline. Document decision in `artifacts/needle-threshold-report.json` for audit.

**Rollback:** set `COOKFULLY_INTELLIGENCE_INLINE_ENABLED=false` and restart API. No data migration; legacy path always authoritative.

## Offline owner erasure

Follow `docs/owner-erasure.md`. Stop web, API, worker, outbox, and retention while leaving PostgreSQL reachable.
The command requires the exact owner UUID/confirmation, an exclusive advisory lease, appendable
independent ledger, and live media/export mounts. `services_running`, ledger preflight failure, or bad
confirmation changes nothing. `owner_erasure_incomplete` means the ledger is already durable: keep
the instance offline and rerun the same command after repairing the dependency. Never remove the
maintenance marker to bypass recovery.
