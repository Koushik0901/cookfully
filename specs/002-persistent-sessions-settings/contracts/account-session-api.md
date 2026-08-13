# Contract: Account & Session API

**Feature**: 002-persistent-sessions-settings
**Status**: Draft — canonical OpenAPI (`/api/openapi.json` and the generated frontend schema) is updated
during implementation to match this contract.

All endpoints below are owner-only and require a browser session (`cookfully_session` cookie). Mutations
additionally require the double-submit `x-csrf-token` header. Errors are RFC 7807 `application/problem+json`.

## Session issuance (modified)

`POST /api/v1/auth/session`

- Request: `{ "email": string, "password": string }` (unchanged).
- Response: `204 No Content` with `Set-Cookie` for `cookfully_session` (HttpOnly) and `cookfully_csrf`
  (JS-readable). Both are now `SameSite=lax` and expire at the session `expires_at` (default 400 days).
- The session `client_label` is populated from the request User-Agent.

## List sessions

`GET /api/v1/auth/sessions`

- Response `200`:
  ```json
  {
    "sessions": [
      {
        "id": "uuid",
        "clientLabel": "Chrome on Windows",
        "createdAt": "2026-08-12T…Z",
        "lastSeenAt": "2026-08-12T…Z",
        "isCurrent": true
      }
    ]
  }
  ```
- Only non-revoked, non-expired sessions are returned, ordered by `last_seen_at` descending. `isCurrent`
  is true for at most one session (the one making the request).

## Revoke a session

`DELETE /api/v1/auth/sessions/{sessionId}`

- `sessionId` is the surrogate UUID. Revoking a session sets `revoked_at`.
- Revoking the current session clears both cookies and behaves like sign-out.
- Response `204 No Content`. Unknown or already-revoked ids return `404`.

## Sign out (existing)

`DELETE /api/v1/auth/session`

- Revokes the current session and clears cookies. Unchanged.

## Change password

`POST /api/v1/auth/password`

- Request: `{ "currentPassword": string, "newPassword": string }`.
- `newPassword` must satisfy the 12–1024 character policy.
- On success: rehash and store the new password, revoke all sessions except the current one.
- Response `204 No Content`. Incorrect `currentPassword` returns `401`; invalid `newPassword` returns
  `422` with a policy message. The account and all sessions are left untouched on any failure.

## Owner preferences (modified)

`GET /api/v1/owner/preferences` and `PUT /api/v1/owner/preferences`

- The `displayName` field is added to both the response and the update payload, alongside the existing
  `timezone`, `weekStartsOn`, and `version`. `email` remains a separate, read-only concern of the UI.
- `version` optimistic concurrency semantics are unchanged.
