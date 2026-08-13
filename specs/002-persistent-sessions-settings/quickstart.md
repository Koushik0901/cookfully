# Phase 1 Quickstart: Persistent Sessions & Account Security Settings

This extends the validated developer workflow from `specs/001-nutrition-recipe-planner/quickstart.md`;
only the delta for this feature is shown.

## Configuration delta

Add one optional setting to `.env` (defaults apply when omitted):

```powershell
COOKFULLY_SESSION_TTL_DAYS=400
```

- Bounded 1–400; the session cookie expiry mirrors this value. Production validation is unchanged and
  still requires `COOKFULLY_COOKIE_SECURE=true` and HTTPS.

## Migrations

```powershell
uv run --directory backend alembic upgrade head
```

The new migration adds a surrogate `id` to `sessions` and is additive — existing session rows and their
original `expires_at` are preserved (no retroactive lifetime change).

## Verify the new surface locally

```powershell
uv run --directory backend pytest tests/integration/test_auth.py tests/integration/test_owner_erasure.py
pnpm --dir frontend test --run
pnpm --dir frontend typecheck
```

## User-visible changes

- Sign in once; the session lasts up to 400 days and survives host/browser restarts unless revoked.
- **Settings** appears in the "Your space" navigation with three tabs: Account (display name, timezone,
  week start), Security (change password, active sessions, sign out), and API access (agent access
  tokens, relocated from the previous `/app/agent-access` route).
- The calendar-preference controls previously inside the goal editor move to Settings → Account.
