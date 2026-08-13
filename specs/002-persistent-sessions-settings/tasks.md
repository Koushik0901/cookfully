# Tasks: Persistent Sessions & Account Security Settings

**Input**: Design documents from `/specs/002-persistent-sessions-settings/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/account-session-api.md

**Tests**: REQUIRED — this feature touches the API contract (session/password endpoints), a background
retention sweep, and a critical user journey (authentication). Integration and contract tests are
mandatory; frontend unit tests cover the Settings page and 401 handling.

**Organization**: Tasks are grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps to user story (US1–US4)
- Exact file paths are included in every task.

---

## Phase 1: Setup

**Purpose**: Configuration surface for the configurable session lifetime.

- [ ] T001 [P] Add `session_ttl_days: int` field (default 400, `Field(ge=1, le=400)`) to `Settings` in `backend/src/cookfully/infrastructure/config.py`
- [ ] T002 [P] Add `COOKFULLY_SESSION_TTL_DAYS: ${COOKFULLY_SESSION_TTL_DAYS:-400}` to the `backend-environment` anchor in `deploy/compose.yaml`
- [ ] T003 [P] Add `COOKFULLY_SESSION_TTL_DAYS=400` to `.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared prerequisites that the session-list and password stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Add surrogate `id` UUIDv7 primary key (and make `id_hash` unique non-PK) to `SessionRecord` in `backend/src/cookfully/infrastructure/models/identity.py`, plus additive migration `backend/migrations/versions/0012_session_surrogate_id.py` (backfill ids, preserve `expires_at`)
- [ ] T005 [P] Add `require_browser_session` dependency (returns owner + session record, enforces CSRF) in `backend/src/cookfully/api/dependencies/auth.py`

**Checkpoint**: Foundation ready — user story implementation can begin.

---

## Phase 3: User Story 1 - Stay signed in across restarts (Priority: P1) 🎯 MVP

**Goal**: A session issued at login lasts up to 400 days (configurable) and is delivered as a
`SameSite=lax` persistent cookie, so the owner is not re-prompted after restarts.

**Independent Test**: Sign in once; close/reopen the browser (simulated via cookie lifetime assertions)
and confirm the session remains valid up to the configured TTL, with no re-login.

### Tests for User Story 1 ⚠️

- [ ] T006 [P] [US1] Integration test: login issues a session with `expires_at == created_at + session_ttl_days` and both cookies are `SameSite=lax` with the matching expiry, in `backend/tests/integration/test_auth.py`
- [ ] T007 [P] [US1] Integration test: a session issued under one TTL is not retroactively extended when `AuthService` is later constructed with a different TTL, in `backend/tests/integration/test_auth.py`

### Implementation for User Story 1

- [ ] T008 [US1] Construct `AuthService(sessions, session_ttl=timedelta(days=resolved.session_ttl_days))` in `backend/src/cookfully/api/main.py` (import `timedelta`)
- [ ] T009 [US1] Change `cookfully_session` and `cookfully_csrf` cookies to `samesite="lax"` in `backend/src/cookfully/api/routes/auth.py`
- [ ] T010 [US1] Populate `client_label` from the User-Agent: derive a short "Browser on OS" label and pass it through `AuthService.login` in `backend/src/cookfully/api/routes/auth.py` and `backend/src/cookfully/application/auth.py`

**Checkpoint**: Persistent sign-in works and is testable independently of the settings UI.

---

## Phase 4: User Story 2 - Settings page with Account/Security/API access (Priority: P2)

**Goal**: A single tabbed Settings page under "Your space" navigation hosts Account (profile prefs),
Security (sign-out), and API access (relocated Agent Access); calendar preferences move off the goal editor.

**Independent Test**: Open Settings from navigation, switch tabs, edit display name/timezone/week start and
observe persistence; confirm the goal editor no longer shows calendar preferences and agent-access is
reachable from Settings.

### Tests for User Story 2 ⚠️

- [ ] T011 [P] [US2] Unit test: Settings page renders Account/Security/API-access tabs and submits profile updates through the API in `frontend/src/features/settings/__tests__/SettingsPage.test.tsx`
- [ ] T012 [P] [US2] Unit test: goal editor no longer renders timezone/week-start controls in `frontend/src/features/goals/__tests__/GoalSettingsPage.test.tsx`

### Implementation for User Story 2

- [ ] T013 [US2] Add `display_name` to the owner preferences read/update path (`OwnerPreferences` schema + `OwnerPreferenceService.update`) in `backend/src/cookfully/api/routes/owner.py` and `backend/src/cookfully/application/owner_preferences.py`
- [ ] T014 [P] [US2] Create `frontend/src/features/settings/SettingsPage.tsx` tabbed shell (Account / Security / API access)
- [ ] T015 [P] [US2] Create `frontend/src/features/settings/AccountTab.tsx` (display name, timezone, week start, read-only email) reusing the owner-preferences API
- [ ] T016 [P] [US2] Create `frontend/src/features/settings/SecurityTab.tsx` with a sign-out control calling `DELETE /api/v1/auth/session` (sessions list and password form arrive in US3/US4)
- [ ] T017 [US2] Add Settings to `SECONDARY_NAVIGATION` and the route tree in `frontend/src/app/App.tsx`; relocate the `agent-access` route under Settings and render `AgentAccessPage` as the API access tab
- [ ] T018 [US2] Remove the "Calendar preferences" disclosure from `frontend/src/features/goals/GoalSettingsPage.tsx`

**Checkpoint**: Settings page is navigable and Account/API-access tabs are functional.

---

## Phase 5: User Story 3 - See and revoke active sessions (Priority: P3)

**Goal**: The owner can list every active session (current flagged) and revoke any of them.

**Independent Test**: Sign in from two browsers, list sessions (both appear, one flagged current), revoke
the other, and confirm it is signed out on its next request.

### Tests for User Story 3 ⚠️

- [ ] T019 [P] [US3] Integration test: two logins yield two listed sessions with exactly one `isCurrent` in `backend/tests/integration/test_auth.py`
- [ ] T020 [P] [US3] Integration test: revoking another session invalidates it on next request while the current session stays valid; revoking the current session clears cookies, in `backend/tests/integration/test_auth.py`
- [ ] T021 [P] [US3] Contract test: sessions list/revoke responses match the contract in `backend/tests/contract/test_account_session_api.py`

### Implementation for User Story 3

- [ ] T022 [US3] Add `AuthService.list_sessions(owner_id, current_id_hash)` and `AuthService.revoke_session(owner_id, session_id)` in `backend/src/cookfully/application/auth.py`
- [ ] T023 [US3] Add `GET /api/v1/auth/sessions` and `DELETE /api/v1/auth/sessions/{sessionId}` in `backend/src/cookfully/api/routes/auth.py` (using `require_browser_session`; revoking current clears cookies)
- [ ] T024 [US3] Add session-list UI (rows, current badge, revoke action) to `frontend/src/features/settings/SecurityTab.tsx` with helpers in `frontend/src/features/settings/api.ts`

**Checkpoint**: Session list and revocation are functional end-to-end.

---

## Phase 6: User Story 4 - Change password (Priority: P4)

**Goal**: The owner can change their password, which invalidates all other sessions and keeps the current
one signed in.

**Independent Test**: Change password with the correct current password, sign out, sign in with the new
password, and verify other sessions were invalidated.

### Tests for User Story 4 ⚠️

- [ ] T025 [P] [US4] Integration test: password change revokes all other sessions and keeps the current one; wrong current password returns 401 and changes nothing; weak new password returns 422, in `backend/tests/integration/test_auth.py`
- [ ] T026 [P] [US4] Contract test: password change request/response matches the contract in `backend/tests/contract/test_account_session_api.py`

### Implementation for User Story 4

- [ ] T027 [US4] Add `AuthService.change_password(owner_id, current_password, new_password)` (Argon2 verify + rehash, revoke all other sessions) in `backend/src/cookfully/application/auth.py`
- [ ] T028 [US4] Add `POST /api/v1/auth/password` in `backend/src/cookfully/api/routes/auth.py`
- [ ] T029 [US4] Add change-password form to `frontend/src/features/settings/SecurityTab.tsx` with a `changePassword` helper in `frontend/src/features/settings/api.ts`

**Checkpoint**: All four user stories are independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Retention, global session-expiry handling, documentation, and verification.

- [ ] T030 [P] Extend `sweep_retention` to delete expired/revoked `sessions` rows older than 30 days in `backend/src/cookfully/jobs/retention.py`, with an integration test in `backend/tests/integration/test_auth.py`
- [ ] T031 Add global 401 handling: invalidate the `["owner-session"]` query on any 401 in `frontend/src/features/recipes/api.ts` so `RequireAuthentication` returns the owner to sign-in
- [ ] T032 [P] Regenerate/verify the OpenAPI schema and `frontend/src/app/api/generated/schema.ts` for the new session/password/preferences endpoints
- [ ] T033 [P] Update `AGENTS.md` "Recent Changes" (persistent 400-day sessions + tabbed Settings page)
- [ ] T034 Run full verification: `uv run --directory backend ruff check .`, `mypy src`, `pytest`; `pnpm --dir frontend lint`, `typecheck`, `test --run`, `build`
- [ ] T035 Validate `quickstart.md` (alembic upgrade, config, tests) and check desktop + 390x844 keyboard/contrast/overflow/loading/empty/error states on the Settings page

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup; BLOCKS US3 and US4 (surrogate id + `require_browser_session`).
- **US1 (Phase 3)**: Depends on Setup (config) only.
- **US2 (Phase 4)**: Depends on Setup + US1 (cookie/auth behavior).
- **US3 (Phase 5)**: Depends on Foundational.
- **US4 (Phase 6)**: Depends on Foundational.
- **Polish (Phase 7)**: Depends on all desired stories.

### User Story Dependencies

- **US1**: Independent after Setup.
- **US2**: Independent of US3/US4; its Security tab is a thin shell until US3/US4 fill it.
- **US3**: Independent of US4.
- **US4**: Independent of US3.

### Within Each User Story

- Write tests first and confirm they fail before implementation.
- Models/services before endpoints; backend before frontend UI for the same story.

### Parallel Opportunities

- T001/T002/T003 run in parallel.
- T006/T007 (US1 tests) in parallel; T011/T012 (US2 tests) in parallel; T019–T021 (US3) and T025–T026 (US4) in parallel.
- US3 and US4 can be implemented in parallel once Foundational is complete.

---

## Parallel Example: User Story 3

```bash
# Launch all US3 tests together:
Task: "T019 integration test two-login session list"
Task: "T020 integration test revoke behavior"
Task: "T021 contract test sessions list/revoke"

# Backend service + route + frontend UI are sequential within the story.
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (US1) and validate persistent sign-in independently.
3. Stop and demo: no re-login across restarts.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → persistent sign-in (headline fix).
3. US2 → Settings page with Account + relocated API access.
4. US3 → session list + revoke.
5. US4 → password change.
6. Polish → retention sweep, 401 handling, docs, full verification.

---

## Notes

- [P] tasks touch different files and can run in parallel.
- `backend/src/cookfully/api/routes/auth.py` is touched by US1 (T009/T010), US3 (T023), and US4 (T028);
  sequence those edits to avoid conflicts (US1 → US3 → US4).
- The existing `test_owner_erasure.py` and `test_openapi_compatibility.py` must continue to pass after the
  `sessions` schema change and new endpoints are added.
- Secrets (session/CSRF tokens, password hashes) stay server-side; do not persist credentials client-side.
- Commit after each logical group.
