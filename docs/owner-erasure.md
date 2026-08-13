# Offline Full-Owner Erasure

Full-owner erasure is an operator-only disaster-sensitive command. It removes the single owner and
the complete owner-controlled namespace: recipes, parsed ingredients, nutrition estimates and
corrections, goals, plans, grocery data, suggestions, pantry data and deductions, sessions, access
tokens, idempotency records, jobs, outbox events, media records/files, encrypted diagnostics, and
portable export archives. USDA reference releases are retained. The command is intentionally absent
from HTTP, MCP, and the browser UI.

This includes first-run state, favorites, recipe collections/memberships/meal roles, shopping stops,
remembered grocery placements, completed-list state, and representative recipe-photo media. Deleting a
collection or shopping stop in normal use is not erasure: memberships or assignments are safely cleared
while recipes and grocery history remain intact.

## Preconditions

Use a disposable restored instance for the first validation. Confirm a recent backup has passed
`backup verify`, its declared expiry/rotation is correct, and the independently preserved erasure
ledger is current, continuous, writable, and replicated. The database must remain reachable, but stop
every process that can read or mutate application state:

```powershell
docker compose -f deploy/compose.yaml stop web api worker outbox retention
```

Do not stop PostgreSQL until the command finishes. The API, Celery worker, outbox dispatcher, and
retention scheduler hold a shared PostgreSQL advisory lease while active; the erasure command requires the exclusive lease and
fails with `services_running` if any remains. A durable
`owner-erasure-maintenance.json` marker beside the independent ledger blocks later service startup
after a ledger-durable partial failure.

Resolve the owner UUID from a verified backup manifest or an authenticated administrative query
before stopping the services. Then run:

```powershell
$ownerId = '<exact-owner-uuid>'
uv run --directory backend cookfully owner erase `
  --owner-id $ownerId `
  --confirm "ERASE OWNER $ownerId" `
  --erasure-ledger ../deploy/erasure-ledger
```

The confirmation is case- and whitespace-sensitive. `--erasure-ledger` must name the independently
preserved live ledger, never a copy embedded in a backup. `COOKFULLY_MEDIA_ROOT` and `COOKFULLY_EXPORT_ROOT` must
resolve to the live managed volumes. All three roots must be distinct and non-overlapping.

## Staged, fail-closed lifecycle

1. Validate the exact confirmation and acquire the exclusive instance lease.
2. Verify ledger continuity and prove the ledger volume can be durably appended.
3. Verify the target is the instance's only owner.
4. Move every managed media/export entry into a hidden quarantine inside its existing volume. Rename
   is same-volume, so no cross-device copy creates a second uncontrolled live copy.
5. Persist the maintenance state and append exactly one content-free `owner`/`owner_owned` record.
6. Delete all non-reference application tables in dependency order and verify every one is empty.
7. Remove the quarantines, verify zero owner-controlled rows, and remove the maintenance marker.

Failure before the ledger append restores every quarantined entry and leaves the database unchanged.
Failure after the append deliberately leaves the marker and quarantines in place. Keep services
stopped, repair the database/filesystem problem, and rerun the identical command. It finds the durable
owner record, does not append another, and idempotently resumes deletion and verification.

Never manually delete the maintenance marker merely to make the application start. If its JSON is
damaged or a quarantine cannot be reconciled, preserve the ledger and quarantines, take a forensic
copy, and recover on a disposable clone. Manually restoring files after an `owner_owned` append would
contradict the ledger and can reintroduce erased content.

## Completion and backup replay

Successful JSON output includes the owner ID, single ledger record ID/cursor, whether work resumed,
and `bootstrap_state: true`. Before restarting, verify the marker is absent, the ledger chain verifies,
and managed roots contain no owner files. Starting the API then performs the normal fresh-owner
bootstrap from the configured bootstrap credentials.

An older backup may still physically contain erased records until its declared rotation expiry. It is
not safe to activate by itself. Restore only through the staged restore command with the current
ledger. The later `owner_owned` record clears every non-reference row and media member before insert;
the restore report must show `active: false`, the replayed record ID, and zero resurrected owner and
recipe IDs. Rotate the old archive on schedule, but retain the ledger record through that expiry plus
the 30-day safety margin.
