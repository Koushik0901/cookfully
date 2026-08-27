# Backup, restore, and portable export

Cookfully uses three deliberately different recovery artifacts:

- A **portable export** is an owner-readable ZIP/NDJSON file for migration or personal custody. It
  includes structured recipes and covers, organization/onboarding state, plans and completed
  grocery lists, owner foods, pantry stock/deductions, and remembered food matches. It excludes
  authentication secrets, sessions, transient jobs, encrypted diagnostics, and erased recipe-owned
  data.
- An **application disaster-recovery archive** captures authoritative PostgreSQL entities plus safe
  managed media. Its erasure-ledger cursor/hash anchor supports the existing fail-closed replay gate.
  It intentionally excludes sessions, idempotency records, processing jobs, outbox events, expired
  diagnostics, and encrypted diagnostics.
- A **database restore point** is an automatic, complete PostgreSQL logical dump. It includes every
  database record—recipes, nutrition, account/session state, job state, outbox, idempotency, and
  reference data—rather than the deliberately narrower application archive.

Redis is not authoritative. Losing it may delay work, but PostgreSQL-backed jobs and outbox records
are the recovery source.

## Host-owned storage

The Compose topology bind-mounts normal host folders beneath `COOKFULLY_DATA_ROOT` (default: `data/`
beside the repository). Docker container and volume deletion therefore cannot delete this state:

| Host folder | Contents | Recovery treatment |
| --- | --- | --- |
| `postgres/` | Application, account, session, job, and nutrition-reference database | Restore from automatic logical dump; do not raw-copy while PostgreSQL is live |
| `media/` | Recipe images and other managed media | Copy to the second backup disk with the matching database dump |
| `backups/database/` | Complete PostgreSQL custom-format dumps, manifests, and checksums | Created automatically; retain a second-disk copy |
| `exports/` | Short-lived one-time portable archives | Useful for owner custody; not the primary DR mechanism |
| `redis/` | Delivery and short-lived coordination | Optional; rebuild from PostgreSQL/outbox |
| `erasure-ledger/` | Append-only erasure records and checkpoints | Replicate independently; restore must never overwrite it |
| `semantic-models/`, `intelligence-models/` | Rebuildable model artifacts | Include in host backup to avoid a slow redownload |

Keep the erasure-ledger replica in a different failure domain and with credentials that the database
backup process cannot use to rewrite history. Replicate each append/checkpoint, monitor lag, and
regularly run continuity verification. A database/media backup without the independently retained
ledger anchor is intentionally not restorable through the application archive gate.

## Automatic database dumps and second-disk copies

The `backup` service runs a complete PostgreSQL dump every day at **02:00 UTC** by default and keeps
the newest **14** successful dumps. It writes an atomic custom-format `.dump`, a SHA-256
checksum, and a manifest before making the restore point visible. Change the defaults in `deploy/.env`:

```dotenv
# Times are UTC because the backup container defaults to UTC.
COOKFULLY_DATABASE_BACKUP_SCHEDULE=02:00
COOKFULLY_DATABASE_BACKUP_RETENTION_COUNT=14
```

Open **Settings → Backups** to see verified restore points or request one immediately. Operators can
also run the same safe sidecar command:

```powershell
docker compose -f deploy/compose.yaml exec -T backup cookfully-database-backup run
```

The database dump does not pretend to be a filesystem backup for recipe images or the independent
ledger. Install the included daily Task Scheduler job to copy database restore points, media, ledger,
exports, and model artifacts to a *different local disk*:

```powershell
.\scripts\backup-cookfully-host.ps1 -DataRoot "D:\Cookfully" -DestinationRoot "E:\Cookfully-backups" -Install
```

The task runs at 03:00 by default, after the database dump. Use the same command with `-RunOnce` to
test it. It deliberately never raw-copies the live `postgres/` directory; it triggers a consistent
logical dump first. Retain at least one known-good copy for the recovery window. Erasure-ledger records
must remain available through the expiry of the last backup that can contain the erased subject,
**plus 30 days**. Ledger checkpoint/segment rotation may occur only after that boundary and must
preserve a verifiable anchor chain.

Portable exports can still be created through the authenticated API job or locally:

```powershell
uv run --directory backend cookfully export create --include-media --output ../artifacts/exports
uv run --directory backend cookfully export verify ../artifacts/exports/<archive>.zip
```

API downloads are owner-authenticated and one-time. Copy a wanted archive immediately; the export
folder is operational scratch space, not durable backup storage.

## Moving old named volumes

For installations created before host-owned storage, use the non-destructive migration helper before
starting this Compose version:

```powershell
.\scripts\migrate-docker-storage.ps1 -DataRoot "D:\Cookfully"
```

It stops Cookfully writers, copies every known named volume only into empty host folders, and preserves
the original volumes as rollback assets. Do not remove those source volumes until a restore drill
succeeds. The tool cannot recover a volume that was already deleted; only a backup made before that
deletion can restore its contents.

## Fail-closed staged restore

Never restore directly into an active instance. First prove a database restore point in a separate,
empty PostgreSQL target with `pg_restore --list` and a disposable database. Then use the application
archive restore gate for database/media activation: it verifies checksums, proves the ledger
cursor/hash anchor, replays every later erasure idempotently, stages media, confirms both targets are
empty, and then activates media. A missing, behind, discontinuous, or hash-invalid ledger rejects the
restore before activation.

For a local disposable target:

```powershell
docker compose -p cookfully-restore-check -f deploy/compose.restore-test.yaml up -d
$targetUrl = 'postgresql+psycopg://cookfully:restore-check-only@localhost:15432/cookfully_restore'
uv run --directory backend alembic -c backend/alembic.ini upgrade head
uv run --directory backend cookfully backup restore --target-database-url $targetUrl --target-media-root ../artifacts/restore-media --erasure-ledger ../deploy/erasure-ledger --staging-root ../artifacts/restore-stage ../artifacts/backups/<archive>.zip
uv run --directory backend cookfully backup compare --target-database-url $targetUrl --erasure-ledger ../deploy/erasure-ledger ../artifacts/backups/<archive>.zip
```

If port 15432 is unavailable on the host, set `COOKFULLY_RESTORE_TEST_PORT` and use the
same port in `$targetUrl`; the disposable database still remains isolated from the live instance.

Set `COOKFULLY_DATABASE_URL=$targetUrl` for the Alembic command if the environment does not already
point at the disposable database. Never point `--target-database-url` or `--target-media-root` at the
active deployment.

For ordinary and recipe-erasure replay, the restore report must show `active: true`, the backup and
current cursors, all replayed record IDs, and zero resurrected recipe IDs. The comparison must report
zero missing and zero unexpected rows. Detached historical meal snapshots and grocery source text
remain; erased recipe-owned entities and media must not.

If a later `owner_owned` record exists, replay intentionally returns an empty bootstrap database and
no managed media. That report must show `active: false` and zero `resurrected_owner_ids` as well as
zero resurrected recipe IDs. Do not start the restored target as though it contained the erased owner;
complete normal fresh-owner bootstrap only after the report and comparison pass. See
`docs/owner-erasure.md` for the destructive workflow and recovery rules.

## Disaster-recovery drill

Run a restore drill at least quarterly and after archive, ledger, migration, or backup-sidecar changes:

1. Verify the candidate dump/archive and the independent ledger replica.
2. Restore into disposable, empty targets and confirm the activation report.
3. Run `backup compare` and require zero differences for application archives.
4. Start an API against the restored target, authenticate, and inspect recipes, corrections, plans,
   grocery provenance, and media.
5. Confirm erased recipes cannot be found and detached history remains readable. If owner erasure is
   under test, instead require bootstrap state and no detached owner history.
6. Destroy only the explicitly named disposable Compose project and its volumes after recording the
   drill result.

Treat any checksum, continuity, resurrection, missing-media, non-empty-target, or comparison failure
as a failed recovery. Preserve the evidence, keep the target inactive, repair the backup/replication
process, and repeat the drill with a new disposable target.
