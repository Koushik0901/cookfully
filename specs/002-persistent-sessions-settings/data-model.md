# Phase 1 Data Model: Persistent Sessions & Account Security Settings

**Date**: 2026-08-12
**Database target**: PostgreSQL 18

## Modeling Conventions

- Same conventions as the base model: UUIDv7 identifiers exposed as strings, timezone-aware UTC
  timestamps, optimistic `version` concurrency on mutable aggregates, and raw secrets never stored or
  exposed. This feature adds no nutrition data and no new JSON columns.

## Identity Changes

### SessionRecord (`sessions`)

The table gains a surrogate public identifier while keeping the token-derived hash private.

| Field | Type | Rules | Change |
|---|---|---|---|
| `id` | UUIDv7 | Primary key; public identifier exposed to the API | **Added** |
| `id_hash` | text (64) | Unique; SHA-256 of the raw token; never exposed | Existing, now unique non-PK |
| `owner_id` | UUID | FK to `owner_accounts.id`, cascade delete | Unchanged |
| `csrf_secret_hash` | text (64) | Required | Unchanged |
| `created_at` | timestamp (tz) | Required | Unchanged |
| `expires_at` | timestamp (tz) | Indexed; `now + session_ttl` at creation | Unchanged; value now configurable |
| `last_seen_at` | timestamp (tz) | Updated on each authenticated request | Unchanged |
| `revoked_at` | timestamp (tz) nullable | Set on revoke/logout | Unchanged |
| `client_label` | text (200) nullable | Browser/device label derived from User-Agent | Existing; now populated at login |

State transitions: `active` (revoked_at null, expires_at in future) → `revoked` (revoked_at set) or
`expired` (expires_at passed). Revocation is terminal; there is no un-revoke.

### OwnerAccount (`owner_accounts`)

No schema change. `display_name` already exists (`String(80)`, non-null) but is not exposed or editable;
it is added to the preferences read/update contract (see `contracts/account-session-api.md`). The email
remains case-insensitive, unique, and read-only in the UI.

### AccessToken (`access_tokens`)

No change. The existing access-token model and management behavior are preserved and merely relocated in
the UI under the Settings → API access tab.

## Relationships

- `OwnerAccount 1 — N SessionRecord` (existing, unchanged).
- `OwnerAccount 1 — N AccessToken` (existing, unchanged).

## Validation Rules

- `session_ttl_days` is an integer from 1 to 400 inclusive; the effective `expires_at` is
  `created_at + session_ttl_days`.
- A session is valid only when `revoked_at IS NULL` and `expires_at > now`; the current-session flag is
  derived by comparing the presented token's hash to `id_hash`.
- `display_name` is 1–80 characters; `timezone` is a valid IANA zone; `week_starts_on` is 1–7.
- A new password must satisfy the existing 12–1024 character policy and differs from the current password
  check is optional but recommended.

## Migration

A single additive Alembic migration on `sessions`:

1. Add `id` UUIDv7 column, backfilled with generated UUIDv7 values.
2. Drop the `id_hash` primary-key constraint and add a unique constraint on `id_hash`.
3. Promote `id` to primary key.

The migration is non-destructive and preserves every existing session row and its original `expires_at`
(no retroactive lifetime change).
