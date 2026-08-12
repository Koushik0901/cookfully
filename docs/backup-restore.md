# Backup, Restore, and Portable Export

Cookfully has two deliberately separate archive formats:

- A **portable export** is owner-readable, versioned ZIP/NDJSON for migration or personal custody. It excludes authentication secrets, sessions, transient jobs, encrypted diagnostics, and erased recipe-owned data. Exact stored decimals retain six places, servings retain three places, and the manifest declares display rounding.
- A **disaster-recovery backup** captures the authoritative PostgreSQL entities plus safe managed media. It excludes sessions, idempotency records, processing jobs, outbox events, expired diagnostics, and encrypted diagnostics. Its manifest includes checksums, expiry, and an erasure-ledger cursor/hash anchor.

Neither Redis nor its volume is authoritative. Losing Redis may delay work, but PostgreSQL-backed jobs and outbox records are the recovery source.

## Docker volumes and protection

The production Compose topology uses separate named volumes:

| Volume | Contents | Recovery treatment |
| --- | --- | --- |
| `postgres-data` | Application and nutrition-reference database | Include in scheduled DR backup |
| `media-data` | Recipe images and other managed media | Include in the same logical backup |
| `export-data` | Short-lived one-time portable archives | Do not treat as DR state |
| `redis-data` | Delivery and short-lived coordination | Optional; never authoritative |
| `erasure-ledger-data` | Append-only erasure records and checkpoints | Replicate independently; restore must never overwrite it |

Keep the erasure-ledger replica in a different failure domain and with credentials that the application backup process cannot use to rewrite history. Replicate each append and checkpoint, monitor lag, and regularly run continuity verification. A database/media backup without its independently retained ledger anchor is intentionally not restorable.

## Schedule and retention

Create a full backup at least daily and before upgrades or data migrations:

```powershell
uv run --directory backend cookfully backup create --output ../artifacts/backups --retention-days 30
uv run --directory backend cookfully backup verify ../artifacts/backups/<archive>.zip
```

Use an external scheduler and rotate only after `backup verify` succeeds. Retain at least one known-good archive for the declared recovery window. Erasure-ledger records must remain available through the expiry of the last backup that can contain the erased subject, **plus 30 days**. Ledger checkpoint/segment rotation may occur only after that boundary and must preserve a verifiable anchor chain.

Portable exports can be created through the authenticated API job or locally:

```powershell
uv run --directory backend cookfully export create --include-media --output ../artifacts/exports
uv run --directory backend cookfully export verify ../artifacts/exports/<archive>.zip
```

API downloads are owner-authenticated and one-time. Copy a wanted archive immediately; the export volume is operational scratch space, not durable backup storage.

## Fail-closed staged restore

Never restore directly into an active instance. Provision a separate, empty PostgreSQL database and empty media directory, apply the same database migrations, and mount a read-only copy of the **current** independent erasure ledger. The restore gate verifies the archive and all checksums, proves the ledger cursor/hash anchor, replays every later erasure idempotently, stages media, confirms both targets are empty, inserts database rows, and then activates media. A missing, behind, discontinuous, or hash-invalid ledger rejects the restore before activation.

For a local disposable target:

```powershell
docker compose -p cookfully-restore-check -f deploy/compose.restore-test.yaml up -d
$targetUrl = 'postgresql+psycopg://cookfully:restore-check-only@localhost:55432/cookfully_restore'
uv run --directory backend alembic -c backend/alembic.ini upgrade head
uv run --directory backend cookfully backup restore --target-database-url $targetUrl --target-media-root ../artifacts/restore-media --erasure-ledger ../deploy/erasure-ledger --staging-root ../artifacts/restore-stage ../artifacts/backups/<archive>.zip
uv run --directory backend cookfully backup compare --target-database-url $targetUrl --erasure-ledger ../deploy/erasure-ledger ../artifacts/backups/<archive>.zip
```

Set `COOKFULLY_DATABASE_URL=$targetUrl` for the Alembic command if the environment does not already point at the disposable database. Never point `--target-database-url` or `--target-media-root` at the active deployment.

For ordinary and recipe-erasure replay, the restore report must show `active: true`, the backup and
current cursors, all replayed record IDs, and zero resurrected recipe IDs. The comparison must report
zero missing and zero unexpected rows. Detached historical meal snapshots and grocery source text
remain; erased recipe-owned entities and media must not.

If a later `owner_owned` record exists, replay intentionally returns an empty bootstrap database and
no managed media. That report must show `active: false` and zero `resurrected_owner_ids` as well as
zero resurrected recipe IDs. Do not start the restored target as though it contained the erased owner;
complete the normal fresh-owner bootstrap only after the report and comparison pass. See
`docs/owner-erasure.md` for the destructive workflow and recovery rules.

## Disaster-recovery drill

Run a restore drill at least quarterly and after archive, ledger, or migration changes:

1. Verify the candidate archive and the independent ledger replica.
2. Restore into disposable, empty targets and confirm the activation report.
3. Run `backup compare` and require zero differences.
4. Start an API against the restored target, authenticate, and inspect recipes, corrections, plans, grocery provenance, and media.
5. Confirm erased recipes cannot be found and detached history remains readable.
   If owner erasure is under test, instead require bootstrap state and no detached owner history.
6. Destroy only the explicitly named disposable Compose project and its volumes after recording the drill result.

Treat any checksum, continuity, resurrection, missing-media, non-empty-target, or comparison failure as a failed recovery. Preserve the evidence, keep the target inactive, repair the backup/replication process, and repeat the drill with a new disposable target.
