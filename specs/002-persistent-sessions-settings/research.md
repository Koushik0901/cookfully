# Phase 0 Research: Persistent Sessions & Account Security Settings

**Date**: 2026-08-12
**Status**: Complete — no unresolved `NEEDS CLARIFICATION` items

## 1. Session persistence model

**Decision**: Keep the existing opaque, server-side session (SHA-256-hashed token, PostgreSQL-backed,
HttpOnly cookie) and change only the lifetime: default 400 days, operator-configurable, with no sliding
renewal. The cookie expiry continues to mirror the session `expires_at`.

**Rationale**: Immich's "stay signed in" behavior is not a client-side token: it issues a 32-byte opaque
token, stores its SHA-256 hash in a `sessions` table, and `validateSession` performs no expiry check — a
session is valid until deleted. Its `immich_access_token` cookie is HttpOnly, `SameSite=lax`, with a
400-day `maxAge` (the browser cookie ceiling). Cookfully already uses the identical mechanism but with a
14-day expiry and no revocation surface, so the fix is lifetime + revocation, not a new auth model. A
long static expiry is simpler than sliding renewal and matches the chosen reference behavior.

**Alternatives considered**:

- **JWT refresh-token rotation**: unnecessary complexity; opaque server-side revocation already provides
  instant revocation, which a stateless JWT cannot without a denylist.
- **Sliding 90-day expiry**: requires re-issuing cookies on activity (extra middleware) for marginal
  security benefit in a single-owner self-hosted context; deferred.
- **"Remember me" checkbox with two session classes**: two lifetimes to model and test for no product
  benefit over always-remembered; rejected.

## 2. Session lifetime configuration

**Decision**: Add `session_ttl_days: int` to `Settings` (default 400, bounded 1–400) and construct
`AuthService(sessions, session_ttl=timedelta(days=resolved.session_ttl_days))` in `api/main.py`.

**Rationale**: `AuthService` already accepts `session_ttl` as a keyword default and tests inject it, so
surfacing it as configuration is low-risk and honors the spec's operator-configurability requirement. The
400-day upper bound matches the browser cookie ceiling so the DB expiry and cookie expiry never diverge.

**Alternatives considered**: A fixed 400-day constant (rejected: not configurable); an unbounded
"never expire" like Immich's raw session rows (rejected: a bounded value keeps the sweep well-defined and
is what the spec promises).

## 3. Session list and revocation

**Decision**: Add a surrogate UUIDv7 `id` as the `sessions` primary key, keep `id_hash` unique, and expose
sessions through `GET /api/v1/auth/sessions` (list, current flagged) and
`DELETE /api/v1/auth/sessions/{sessionId}` (revoke). Populate the existing-but-unused `client_label` from
the request User-Agent at login.

**Rationale**: `id_hash` is the SHA-256 of the raw token and must never leave the server, so a public
identifier is required for the API to address a session. UUIDv7 matches the project's identifier
convention. A device/browser label gives the owner a recognizable handle, mirroring Immich's session
metadata. The current session is flagged by comparing the presented token hash against each row's
`id_hash`, so no session id is ever derived from the cookie directly.

**Alternatives considered**: Exposing `id_hash` directly (rejected — leaks a token-derived secret);
storing a separate `public_id` column alongside the surrogate key (rejected — redundant).

## 4. Password change

**Decision**: Add `POST /api/v1/auth/password` taking `currentPassword` and `newPassword`; verify the
current password with Argon2, enforce the existing minimum-strength policy, rehash, and revoke all other
sessions while keeping the current one.

**Rationale**: Matches Immich's change-password + `invalidateSessions` behavior and fixes a real gap
(today the password is fixed at bootstrap with no change path). Argon2's `check_needs_rehash` is reused so
parameter upgrades rehash transparently, consistent with the existing login path.

**Alternatives considered**: Revoking the current session too (rejected — Immich keeps the current session
and it avoids an unnecessary immediate sign-out); a separate "forgot password" flow (rejected — single
owner, self-hosted, no email service).

## 5. Settings page information architecture

**Decision**: A single `/app/settings` page with three tabs — **Account** (display name, timezone, first
day of week, read-only email), **Security** (password change, active-sessions list with revoke, sign-out),
and **API access** (the existing Agent Access page, relocated). Move timezone/week-start editing out of
the goal editor so there is a single source of truth.

**Rationale**: Immich consolidates account, sessions, and API keys under one Settings surface with tabs,
which is the pattern the owner asked for. Relocating Agent Access also fixes its current unreachability
(no navigation link today) while honoring the earlier decision to keep it out of kitchen navigation.
Timezone/week-start are account preferences, not goal targets, so they belong in Account.

**Alternatives considered**: A standalone account page plus a separate security page (rejected — more
navigation for no benefit); leaving calendar preferences in the goal editor and duplicating them in
Account (rejected — two sources of truth violate the constitution's data-integrity spirit).

## 6. Mid-session expiry handling

**Decision**: Add a single global 401 handler in the shared `apiRequest` helper that invalidates the
`["owner-session"]` query, causing `RequireAuthentication` to re-probe and render sign-in instead of
per-page errors.

**Rationale**: With 400-day sessions, the only way a session ends unexpectedly is revocation or an
operator TTL change. Today only the boot probe treats 401 specially; any in-flight request that hits an
expired/revoked session surfaces a generic per-page error. A single invalidate point keeps the transition
to sign-in consistent and avoids touching every feature page.

**Alternatives considered**: Per-page 401 handling (rejected — error-prone and duplicated); full-page
redirect on 401 (rejected — the existing inline sign-in pattern is the established UX).

## 7. Retention sweep

**Decision**: Extend `sweep_retention` to delete `sessions` rows that are expired or revoked and older
than a bounded 30-day grace period.

**Rationale**: Long-lived sessions that are revoked or superseded would otherwise accumulate unbounded
with no cleanup today. A grace period preserves forensic context (last activity) briefly while keeping
the table small. The sweep is already idempotent and runs on the existing retention process.

**Alternatives considered**: Immediate deletion on revoke (rejected — loses last-activity audit context);
no cleanup (rejected — unbounded growth).

## 8. Cookie `SameSite` change

**Decision**: Change the `cookfully_session` and `cookfully_csrf` cookies from `SameSite=strict` to
`SameSite=lax`.

**Rationale**: With `strict`, a top-level navigation initiated from another site or dashboard (e.g., a
Homepage/Heimdall bookmark grid — the standard self-hosted pattern) does not carry the cookie, so the
owner briefly sees the sign-in screen despite holding a valid session. `lax` sends the cookie on top-level
GET navigations while still blocking cross-site POST, and Cookfully's double-submit CSRF header continues
to protect mutations. This matches Immich.

**Alternatives considered**: Keeping `strict` (rejected — the external-link papercut contradicts the
"less friction" goal); dropping CSRF entirely with `lax` (rejected — the header check is retained).
