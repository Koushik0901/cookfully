# Production self-hosting

This guide deploys one Cookfully owner/household with Docker Compose. PostgreSQL is authoritative,
Redis is delivery/coordination only, and the erasure ledger is an independent safety dependency that
must survive database and media restore.

## Host and secrets

Use a maintained x86-64 Linux host, Docker Engine with Compose v2, persistent SSD-backed Docker
storage, a DNS name, and a TLS-terminating reverse proxy. Keep the repository and `.env` readable only
by the deployment account. Generate a stable UUID once, a database password, a 32-byte-or-longer
application secret, and a strong bootstrap password; do not rotate `COOKFULLY_SECRET_KEY` without first
accounting for encrypted diagnostics.

Minimum production `.env` values:

```dotenv
COOKFULLY_ENVIRONMENT=production
COOKFULLY_INSTANCE_ID=replace-with-one-stable-random-uuid
COOKFULLY_SECRET_KEY=replace-with-a-random-secret-of-at-least-32-characters
COOKFULLY_OWNER_EMAIL=owner@example.com
COOKFULLY_OWNER_BOOTSTRAP_PASSWORD=replace-with-a-strong-bootstrap-password
COOKFULLY_PUBLIC_BASE_URL=https://recipes.example.com
COOKFULLY_API_BASE_URL=https://recipes.example.com
COOKFULLY_COOKIE_SECURE=true
COOKFULLY_PROXY_SUBNET=172.31.250.0/24
COOKFULLY_WEB_PROXY_IP=172.31.250.10
COOKFULLY_TRUSTED_PROXY_CIDRS=172.31.250.10/32
COOKFULLY_FAILED_IMPORT_DIAGNOSTICS_ENABLED=false
COOKFULLY_RETENTION_SWEEP_INTERVAL_SECONDS=21600
COOKFULLY_BACKUP_RETENTION_DAYS=30
POSTGRES_DB=cookfully
POSTGRES_USER=cookfully
POSTGRES_PASSWORD=replace-with-a-random-database-password
```

Choose a non-conflicting proxy subnet. The web container has the fixed address named by
`COOKFULLY_WEB_PROXY_IP`; the API accepts forwarded headers only from `COOKFULLY_TRUSTED_PROXY_CIDRS`. Keep those
values aligned. Do not use `*` or trust the public internet. Production validation rejects HTTP base
URLs, insecure cookies, an empty/invalid proxy allowlist, development secrets, or the default
instance ID.

## Compose topology

Validate and start the merged production configuration:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml config --quiet
docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml up -d --build
docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml ps
```

PostgreSQL and Redis have no published production ports. The API is reachable only on the backend and
proxy networks. The web gateway binds to `127.0.0.1:8080` by default, so TLS must terminate on the same
host or reach it through an equivalently private tunnel. Do not add untrusted containers to the proxy
network. All containers enable `no-new-privileges`; database, media, exports, Redis, and ledger use
separate named volumes.

## TLS and trusted headers

Example Caddy host configuration:

```caddyfile
recipes.example.com {
    reverse_proxy 127.0.0.1:8080 {
        header_up Host {host}
        header_up X-Forwarded-Proto https
    }
}
```

An nginx, Traefik, or managed proxy is also valid if it redirects HTTP to HTTPS, presents a valid
certificate, preserves the external `Host`, and sets `X-Forwarded-Proto: https`. The bundled web
gateway passes only an exact `https` forwarded value; otherwise it uses its connection scheme. Uvicorn
then accepts proxy headers only from the configured web-container CIDR. Verify from outside the host
that authentication sets a `Secure`, `HttpOnly`, `SameSite=Lax` session cookie and that plain HTTP
redirects before credentials are sent.

## Retention and diagnostics

The `retention` service performs a sweep immediately at startup and every six hours by default,
comfortably inside the 24-hour failed-import diagnostic boundary. It deletes expired diagnostic
media, reduces detailed terminal-job diagnostics at 30 days, removes safe job metadata at one year,
and expires idempotency records. Its health check fails when the heartbeat is older than two sweep
intervals. Alert on an unhealthy or restarting retention container.

Failed-import HTML remains disabled unless explicitly enabled. When enabled, it is encrypted with a
key derived from `COOKFULLY_SECRET_KEY`, registered with a 24-hour expiry, and excluded from portable exports
and disaster-recovery backups. Successful-import HTML and raw structured-provider payloads are never
retained. Prefer leaving diagnostics off; enable them only for a bounded investigation, then confirm a
successful retention sweep.

## Volumes, backup, and ledger replication

| Volume | Purpose | Backup treatment |
| --- | --- | --- |
| `postgres-data` | App records and imported nutrition references | Daily verified DR backup |
| `media-data` | Recipe images and managed safe media | Same logical DR backup as PostgreSQL |
| `export-data` | One-time portable-export scratch data | Rotate; not authoritative DR state |
| `redis-data` | Delivery and short-lived coordination | Optional; rebuild from PostgreSQL/outbox |
| `erasure-ledger-data` | Content-free append-only erasure chain | Replicate independently; never overwrite from backup |

Create and verify a backup daily and before every upgrade:

```bash
docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml exec -T api \
  cookfully backup create --output /data/exports --retention-days 30
docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml exec -T api \
  cookfully backup verify /data/exports/REPLACE_WITH_ARCHIVE.zip
```

Copy verified archives out of `export-data` to protected storage. An external scheduler must delete
only expired archives that have a newer verified replacement. Keep at least one known-good archive and
run a clean restore drill quarterly. Follow `docs/backup-restore.md`; archive creation is not proof of
recoverability.

Replicate `erasure-ledger-data` separately to append-preserving storage in another failure domain,
using credentials that the database/media backup job cannot use to rewrite history. Copy only after
filesystem flush, verify the complete hash chain at the replica, monitor replication lag, and retain
each record through the latest possibly containing backup expiry plus 30 days. A restore always mounts
the current replica read-only and fails closed if its cursor is behind, missing, or discontinuous.

## Health and operation

```bash
curl --fail --silent http://127.0.0.1:8080/api/v1/health
docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml ps
docker compose -f deploy/compose.yaml -f deploy/compose.production.yaml logs --since=15m api worker outbox retention
```

Admit traffic only when PostgreSQL, Redis, API, web, and retention report healthy and worker/outbox are
stable. Correlate failures with `X-Request-ID`/job `traceId`; never collect cookies, bearer tokens, raw
provider payloads, private goals, or diagnostic HTML in ordinary logs.

## Upgrade and rollback

1. Read release and dependency notes; verify a fresh backup and the independently replicated ledger
   head.
2. Stop traffic and background mutation: `docker compose -f deploy/compose.yaml -f
   deploy/compose.production.yaml stop web worker outbox retention api`.
3. Pull the reviewed source/image revision. Do not use an unreviewed floating deployment revision.
4. Start PostgreSQL and Redis, then run migrations once with `docker compose -f deploy/compose.yaml -f
   deploy/compose.production.yaml run --rm -e COOKFULLY_RUN_MIGRATIONS=false api alembic upgrade head`.
5. Start API, outbox, worker, retention, then web; check migration head, health, login, one recipe read,
   one queued job, media access, and the next retention heartbeat.

Roll back application images only when the database migration is explicitly backward compatible.
Otherwise restore a verified archive into a clean target and require current-ledger replay before
activation. Never restore over the live volumes.

For offline full-owner erasure, stop `web`, `api`, `worker`, `outbox`, **and `retention`** while leaving
PostgreSQL reachable, then follow `docs/owner-erasure.md` exactly.

## Comparative operations note

`docs/inspiration-review.md` compares this lifecycle with Mealie, Tandoor Recipes, and Immich. Their
integrated backups, deployment guidance, maintenance mode, and integrity checks are useful reference
points, but they solve different scopes and have their own documented limitations. Cookfully's
external scheduler and independent erasure ledger add operator burden; they are retained because the
specified zero-resurrection guarantee cannot be met by treating an application archive as the only
recovery authority. Reassess this tradeoff with operational evidence rather than assuming either
approach is universally better.
