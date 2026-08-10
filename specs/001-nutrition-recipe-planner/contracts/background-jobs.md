# Background Job Contract

## Purpose

This contract defines durable work shared by the API, PostgreSQL outbox dispatcher, Redis broker, and
Celery worker. PostgreSQL is authoritative; Celery task state is diagnostic only.

## Versioned Envelope

```json
{
  "schemaVersion": 1,
  "jobId": "019c...",
  "kind": "nutrition_rollup",
  "aggregateType": "recipe",
  "aggregateId": "019c...",
  "inputHash": "sha256:...",
  "traceId": "019c...",
  "requestedAt": "2026-08-09T18:00:00Z"
}
```

The broker payload MUST contain identifiers, versions, hashes, and tracing only. It MUST NOT contain
recipe HTML, provider credentials, user goals, session data, or authoritative nutrition values.

## Job Kinds

| Kind | Input aggregate | Result |
|---|---|---|
| `recipe_import` | Import placeholder recipe + normalized URL | Captured source fields, ingredients, instructions, media reference |
| `ingredient_parse` | Recipe | Structured ingredient fields and parser provenance |
| `nutrition_match` | Recipe | Food candidates/matches, gram conversions, assumptions |
| `nutrition_rollup` | Recipe | Immutable NutritionEstimate and active estimate swap |
| `portable_export` | Owner | Versioned ZIP and checksum manifest |
| `restore_validate` | Uploaded backup/export | Staged compatibility and checksum report; never commits automatically |
| `suggestion` | SuggestionRun (P4) | Feasible/infeasible result and projected snapshots |

## State and Retry Semantics

```text
queued -> running -> succeeded
                  \-> retry_wait -> queued
                  \-> failed
queued|retry_wait -> cancelled
queued|running|retry_wait -> superseded
```

- The API transaction creates the domain mutation, ProcessingJob, and OutboxEvent together.
- The dispatcher publishes an unpublished outbox event and records `published_at`; duplicate publish is
  allowed.
- The worker locks the job row, verifies it is eligible, and compares the current aggregate input hash.
  A mismatch transitions the job to `superseded` without writing results.
- A worker MAY receive the same envelope more than once. Each handler MUST return the existing terminal
  result or continue from authoritative state without duplicating estimates, media, plan entries, or
  exports.
- Retryable failures include timeouts, rate limits, broker interruptions, and provider 5xx responses.
  Invalid input, blocked URLs, schema-invalid provider output after bounded attempts, and missing
  authoritative records are terminal.
- Retries use bounded exponential backoff with jitter. Default maximum is five attempts; job-specific
  changes require configuration and tests.
- `failure_code` is stable and safe for UI/API use. Internal stack traces stay in protected logs.
- A heartbeat/reconciler returns stalled `running` jobs to `queued` only when their handler is proven
  idempotent.

## Progress and Chaining

Recipe processing is an explicit chain:

```text
recipe_import -> ingredient_parse -> nutrition_match -> nutrition_rollup
```

Each successful step writes its own authoritative result before enqueueing the next step. Partial
ingredient matches may still proceed to rollup with reduced coverage. A terminal step failure sets the
recipe to `partial` when useful results exist, otherwise `failed`. The recipe remains manually editable.

## Observability

Every log and metric includes `job_id`, `kind`, `aggregate_id`, `attempt`, `trace_id`, duration, and
outcome. Metrics count queue delay, run duration, retry count, stale/superseded results, failure codes,
and reconciliation actions. Logs MUST NOT include raw page bodies, prompts, secrets, or personal goals.

## Contract Tests

- Duplicate delivery produces one active result.
- Worker death after result write and before acknowledgement remains idempotent.
- Input change during execution prevents stale result activation.
- Broker outage leaves an unpublished outbox event that is later dispatched.
- Retry exhaustion produces a stable failure code and recoverable user action.
- Manual corrections survive every job kind unless an explicit reset command preceded the job.
