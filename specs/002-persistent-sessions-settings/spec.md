# Feature Specification: Persistent Sessions & Account Security Settings

**Feature Branch**: `002-persistent-sessions-settings`
**Created**: 2026-08-12
**Status**: Draft
**Input**: User description: "Stay signed in across computer restarts like Immich (no re-login every restart), and add a settings page with account and security tabs inspired by Immich."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Stay signed in across restarts (Priority: P1)

As the owner, I want to sign in once and stay signed in, so I am not asked for my
password every time I restart my computer or return to the app after several days.

**Why this priority**: This is the primary complaint and the headline value. Re-entering
credentials every restart is direct friction against the core plan/cook/eat workflow, and
the reference behavior (Immich) already demonstrates that a self-hosted single-owner app
can safely remember its owner for a very long period.

**Independent Test**: Sign in once, close the browser and/or restart the host, then reopen
the app and confirm it lands directly on the planner without any sign-in prompt.

**Acceptance Scenarios**:

1. **Given** the owner has signed in successfully, **When** they close and reopen the app
   (including a full computer restart within the session lifetime), **Then** they are taken
   straight to the planner home without being asked to sign in again.
2. **Given** a signed-in owner, **When** the session reaches its lifetime, **Then** they are
   returned to the sign-in screen with a clear message rather than a broken page.
3. **Given** a session was issued before the lifetime changed, **When** the owner returns,
   **Then** the session still honors its original expiry rather than being retroactively extended.

---

### User Story 2 - A single Settings page with Account, Security, and API access (Priority: P2)

As the owner, I want one obvious Settings page organized into tabs, so I can find everything
about my account and security in one place instead of scattered or hidden.

**Why this priority**: It is the home for the security controls that long-lived sessions
require, and it fixes real gaps today: there is no sign-out control anywhere, no way to
change the password, and the existing API-access page is unreachable from navigation.

**Independent Test**: From the app navigation, open Settings and see Account, Security, and
API access sections; update account details and observe the change persist.

**Acceptance Scenarios**:

1. **Given** the owner is signed in, **When** they open the primary navigation, **Then** a
   Settings entry is present and opens the Settings page.
2. **Given** the Account tab, **When** the owner updates display name, timezone, or first
   day of the planning week, **Then** the change is saved and reflected everywhere those
   values are used; the sign-in email is shown but read-only.
3. **Given** the Security tab, **When** the owner opens it, **Then** a sign-out control and
   password-change control are available.
4. **Given** the API access tab, **When** the owner opens it, **Then** existing
   access-token management (create, list, revoke, one-time secret reveal) is available with
   no loss of current functionality.

---

### User Story 3 - See and revoke active sessions (Priority: P3)

As the owner, I want to see every signed-in session and revoke any of them, so a device I no
longer control cannot keep accessing my data.

**Why this priority**: It completes the security model that makes long-lived sessions safe.
With sessions persisting for ~400 days, revocation — not expiry — is the owner's primary
control over access.

**Independent Test**: Sign in from two separate browsers, view the session list, revoke the
second browser's session, and confirm that browser is signed out on its next request while
the first remains signed in.

**Acceptance Scenarios**:

1. **Given** multiple active sessions, **When** the owner opens the Security tab, **Then**
   every session is listed with a recognizable label, sign-in time, last-activity time, and
   the current session is clearly marked.
2. **Given** a list of sessions, **When** the owner revokes a session that is not the current
   one, **Then** that session is invalidated on its next request and disappears from the list.
3. **Given** the owner revokes the current session, **Then** they are signed out immediately.

---

### User Story 4 - Change password (Priority: P4)

As the owner, I want to change my password, so I can rotate credentials; changing it should
sign out my other sessions.

**Why this priority**: Today the password is fixed at the value set during first setup with
no way to change it. This is a basic security requirement and the natural companion to
session management.

**Independent Test**: Change the password with the correct current password, then verify the
old password no longer works and the new one does, and that all other sessions are signed out.

**Acceptance Scenarios**:

1. **Given** the owner supplies the correct current password and a valid new password,
   **When** they submit, **Then** the password is changed and the owner can sign in with the
   new password.
2. **Given** the owner supplies an incorrect current password, **When** they submit, **Then**
   the change is rejected with a clear message and nothing is altered.
3. **Given** a successful password change, **When** other sessions are checked, **Then** they
   are invalidated while the current session remains signed in.

---

### Edge Cases

- A session expires or is revoked while the app is open: the next action must return the owner
  to the sign-in screen with a clear message, not a generic per-page error.
- The owner account has no display name: the Account tab shows the email as the fallback label.
- Revoking the current session from another device: the current-session flag is computed per
  session, so no two sessions are ever both marked current in the same view.
- A password change is attempted with a new password that fails the strength policy: reject with
  a clear message and leave the account and all sessions untouched.
- Stale expired or revoked session records: these are removed after a bounded grace period so
  the list and storage do not grow without limit.
- Timezone and week-start values previously edited in the goal editor: after moving them to the
  Account tab there must be a single place to edit them, and the goal editor no longer exposes a
  competing control.

## Constitution Alignment *(mandatory)*

- **Macro-goal contribution**: Reduces sign-in friction in the primary plan/cook/eat workflow by
  removing repeated re-authentication, and adds the account/security controls the owner needs to
  stay in that workflow safely. It does not add any new planning, nutrition, or archive capability.
- **Nutrition and estimation impact**: N/A. No calorie/macro values, provenance, serving basis, or
  correction behavior are affected.
- **Structured processing**: A bounded background retention sweep removes stale session records;
  it is idempotent and independent of nutrition processing. No AI or model calls are involved.
- **Data and agent access**: Adds owner-only session-management endpoints gated by the existing
  browser-session authentication. Agent/MCP access tokens are unchanged in scope; secrets (session
  tokens, CSRF tokens, password hashes) remain server-side only (Principle IV). Session records are
  backed up and exported like other PostgreSQL data, and the retention increase is justified by the
  single-owner threat model (a self-hosted personal instance) rather than a multi-user one.
- **Reuse and experience**: Adopts Immich's persistent-session and session-list model (verified
  against Immich source: a long-lived opaque token hashed at rest, valid until revoked). The
  comparison is recorded in `docs/inspiration-review.md`. UI follows `DESIGN.md` tokens and must
  handle loading, empty, partial, and error states at desktop and narrow mobile widths with keyboard
  access.
- **Explicit non-goals**: No multi-user administration, no instance stats dashboard, no background
  jobs admin page, no database-backed system-settings editor, no OAuth, no "remember me" toggle, and
  no sliding session renewal in this feature.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: An owner who has signed in once MUST remain signed in for an extended default period
  (400 days, the browser cookie ceiling) without re-entering credentials, unless the session is
  explicitly revoked or invalidated by a password change.
- **FR-002**: The session lifetime MUST be configurable by the self-hosting operator, and the
  effective expiry MUST be reflected in the sign-in state delivered to the browser.
- **FR-003**: The app MUST provide a single Settings destination reachable from primary navigation,
  organized into at least Account, Security, and API access sections.
- **FR-004**: The Account section MUST let the owner view and update display name, timezone, and
  first day of the planning week; the sign-in email MUST be shown read-only.
- **FR-005**: The Security section MUST list every active session with a recognizable label,
  sign-in time, last-activity time, and an indicator distinguishing the current session.
- **FR-006**: The owner MUST be able to revoke any listed session, and revocation MUST invalidate
  that session on its next request.
- **FR-007**: The owner MUST be able to sign out, which revokes the current session and clears the
  sign-in state.
- **FR-008**: The owner MUST be able to change their password by supplying the current password and
  a new password meeting the existing minimum-strength policy.
- **FR-009**: A successful password change MUST invalidate all other sessions while keeping the
  current session signed in.
- **FR-010**: The API access section MUST expose existing access-token management (create, list,
  revoke, one-time secret reveal) with no loss of current functionality.
- **FR-011**: When a session expires or is revoked while the app is open, the app MUST return the
  owner to the sign-in screen with a clear message rather than show a broken page.
- **FR-012**: Expired and revoked session records MUST be periodically removed after a bounded
  grace period.
- **FR-013**: Session tokens, CSRF tokens, and password hashes MUST remain server-side and MUST NOT
  be stored in the browser or appear in logs.
- **FR-014**: Changing the session lifetime MUST NOT retroactively extend already-issued sessions;
  each session expires per the lifetime in effect when it was created.

### Key Entities

- **Owner account** (existing): the single user; holds display name, sign-in email, timezone, first
  day of the planning week, and the password credential.
- **Session**: a sign-in record with creation time, last-activity time, expiry, a human-recognizable
  device/browser label, and a revocation status; the owner can list, identify, and revoke these.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After one successful sign-in, the owner can close and reopen the app across a device
  restart with no sign-in prompt for 400 days.
- **SC-002**: The owner can find and complete account, session, and password management without
  leaving a single Settings page.
- **SC-003**: Revoking a session from another device signs out that device on its next request
  within a single round trip.
- **SC-004**: Every account/security action surfaces explicit success or failure feedback; no
  operation fails silently.

## Assumptions

- The product remains single-owner; no multi-user administration is introduced (consistent with the
  constitution and the existing single-owner scope).
- The default session lifetime is 400 days to match the browser cookie ceiling and Immich's behavior,
  and is operator-configurable.
- There is no "remember me" checkbox — always-remembered is the default, matching Immich.
- Timezone and first-day-of-week preferences relocate from the goal editor to the Account tab so
  there is a single place to edit them.
- Sliding session renewal is out of scope; a long static expiry plus explicit revocation is the
  simpler, Immich-equivalent model.
- Instance stats, background jobs administration, and a settings editor are deferred and are not
  part of this feature.
