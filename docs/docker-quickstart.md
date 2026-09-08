# Docker quickstart: run Cookfully on your machine

The fastest way to try Cookfully is the published Docker Compose release. It runs the web client,
API, workers, PostgreSQL, and Redis from public images. No repository checkout or Node, Python, or
`uv` install is needed — only Docker.

For the development workflow (live-reloading API and client, tests, CLI tools), use the
[development quickstart](../specs/001-nutrition-recipe-planner/quickstart.md) instead. For a
production deployment with TLS and a reverse proxy, see [self-hosting](self-hosting.md).

## Prerequisites

- Docker Engine with the Compose v2 plugin, or Docker Desktop
- ~4 GB free RAM and ~5 GB free disk for the first image pull and application data

## 1. Download the release Compose files

The release bundle is intentionally just the deployment files. Download the pinned `v0.1.0`
Compose file and secret-free environment template into a small deployment directory:

```bash
mkdir -p cookfully/deploy
curl -fsSL https://raw.githubusercontent.com/Koushik0901/cookfully/v0.1.0/deploy/compose.yaml \
  -o cookfully/deploy/compose.yaml
curl -fsSL https://raw.githubusercontent.com/Koushik0901/cookfully/v0.1.0/deploy/.env.example \
  -o cookfully/deploy/.env.example
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path 'cookfully\deploy' | Out-Null
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Koushik0901/cookfully/v0.1.0/deploy/compose.yaml' -OutFile 'cookfully\deploy\compose.yaml'
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/Koushik0901/cookfully/v0.1.0/deploy/.env.example' -OutFile 'cookfully\deploy\.env.example'
```

## 2. Create the environment file

Compose fails closed without secrets: it refuses to start until `deploy/.env` exists with the three
required values. Copy the template and fill them in.

```powershell
Copy-Item -LiteralPath 'cookfully\deploy\.env.example' -Destination 'cookfully\deploy\.env'
```

On bash, run `cp cookfully/deploy/.env.example cookfully/deploy/.env`.

Open `cookfully/deploy/.env` and replace the three required placeholders:

| Variable | Purpose | Example value |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | Database password | `ChangeMe-Database-2026` |
| `COOKFULLY_SECRET_KEY` | Session signing / diagnostics key, 32+ chars | `openssl rand -hex 32` output |
| `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD` | Sign-in password for the single owner account | `ChangeMe-Owner-2026!` |

The owner email defaults to `owner@example.com`; set `COOKFULLY_OWNER_EMAIL` in the same file to
change it. Everything else already has a working local default.

> `.env` contains secrets. Keep it private and never commit or share it.

## 3. Choose the persistent data location

`COOKFULLY_DATA_ROOT` is the one host path you choose for Cookfully's durable state. The template
sets it to `../data`, which creates a `data/` folder beside the downloaded `deploy/` directory. To
use another disk, edit only this value before starting, for example:

```dotenv
# cookfully/deploy/.env
COOKFULLY_DATA_ROOT=D:/Cookfully
```

No Compose-file edits are normally required. The Compose file bind-mounts these subfolders beneath
the selected root:

| Folder | Persisted state |
| --- | --- |
| `postgres/` | Cookfully database, recipes, plans, groceries, nutrition, accounts, and jobs |
| `media/` | Recipe photos and managed media |
| `exports/` | Portable export archives while they are retained |
| `backups/` | Automatic PostgreSQL dumps, checksums, manifests, and backup requests |
| `erasure-ledger/` | Independent append-only erasure records and checkpoints |
| `semantic-models/` | Rebuildable semantic-matching model artifacts |
| `intelligence-models/` | Optional Needle2 model artifact |
| `redis/` | Redis AOF and short-lived coordination state |

The `.env` file and Compose files live outside this root, so back up the `.env` securely as
configuration. Temporary files, health heartbeats, container logs, and browser caches are
intentionally not durable application data.

`docker compose down` removes containers and networks but leaves this host folder untouched. Do not
delete the selected data root unless you intend to destroy the instance; use the backup and restore
guidance for migration or recovery.

If you change `COOKFULLY_DATA_ROOT` later, Cookfully will see that path as a new instance unless you
copy or restore the existing data into it first. Stop the stack and complete a backup/restore or
careful host-folder migration before switching paths.

## 4. Pull and start the stack

From the deployment directory:

```bash
cd cookfully
docker compose -f deploy/compose.yaml pull
docker compose -f deploy/compose.yaml up -d --no-build
```

The first pull downloads the locked release images. It starts the web client, API, workers,
PostgreSQL, Redis, retention worker, storage initializer, and automatic backup service. The API
runs database migrations automatically on first start and creates the owner account from
`COOKFULLY_OWNER_*`.

Check that everything is healthy:

```bash
docker compose -f deploy/compose.yaml ps
```

Wait until `api`, `postgres`, `redis`, `web`, `retention`, and `backup` report `healthy`.

## 5. Release images and tags

The Compose file defaults to the pinned `v0.1.0` images. To move to a later release, set
`COOKFULLY_IMAGE_TAG` in `cookfully/deploy/.env`, then run `docker compose -f deploy/compose.yaml
pull` and `docker compose -f deploy/compose.yaml up -d --no-build` again. The images are
`ghcr.io/koushik0901/cookfully-api`, `cookfully-web`, `cookfully-intelligence`, and
`cookfully-backup`; PostgreSQL and Redis continue to use their upstream images.

## 6. Open the app

Visit <http://localhost:8080> and sign in with:

- Email: the value of `COOKFULLY_OWNER_EMAIL` (default `owner@example.com`)
- Password: the value of `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD`

The API health endpoint is at <http://localhost:8080/api/v1/health>; the OpenAPI document is at
<http://localhost:8080/api/openapi.json>.

### Open it from a phone

`localhost` works only on the computer running Docker. For a trusted-LAN test, open
`http://<server-lan-ip>:8080` on the phone while both devices share Wi-Fi. For a durable deployment,
use the production HTTPS profile and follow [Mobile and PWA deployment](mobile-pwa.md), including
the optional Tailscale MagicDNS path.

## What you can try

- Write a recipe from memory or import one from a public recipe URL
- Plan meals by week or day, adjust servings, and open the grocery list
- Set weekly goals and read the nutrition guidance next to planning
- Create owner foods, favorites, collections, and meal moments
- Create a scoped API token under Settings → Connections for external assistants

## Nutrition reference data (optional)

Nutrition estimates work without any setup: ingredients that cannot be matched to a reference
food are simply excluded from the coverage ratio. To raise estimate quality, install the USDA
FoodData Central datasets from inside the app:

- On first run, the welcome journey offers a "Real nutrition numbers?" step (Foundation + SR
  Legacy, optionally Branded foods).
- Later, use Settings → Nutrition data.

The app downloads the official bulk files, imports them into PostgreSQL, and activates them in the
background — no local tools or manual files are needed. Operators who prefer the CLI can still use
`cookfully reference-data import` + `activate` (see the development quickstart, section 4).

## Development from source (optional)

Clone the repository only when you want to modify Cookfully or build images locally:

```bash
git clone https://github.com/Koushik0901/cookfully.git
cd cookfully
cp deploy/.env.example deploy/.env
docker compose -f deploy/compose.yaml up -d --build
```

## Rebuilding after a code change

For a source checkout, frontend and backend images are built from the repository. Pull new commits
and rebuild the affected image:

```bash
git pull
docker compose -f deploy/compose.yaml up -d --build
```

To rebuild only the web client (fastest loop): `docker compose -f deploy/compose.yaml up -d --build web`.

## Stopping and removing

```bash
# Stop everything. Your data remains in COOKFULLY_DATA_ROOT.
docker compose -f deploy/compose.yaml down
```

Docker can remove containers without touching `COOKFULLY_DATA_ROOT`. Do not delete that folder to
reset the app: it contains the kitchen itself. Automatic database dumps and a second-disk host backup
task are described in [backup and restore](backup-restore.md).

## Moving an older named-volume installation

If Cookfully was first started before host storage was introduced, copy its old volumes before
starting this version. The migration stops writers, copies each known volume to the selected host
folder, and intentionally leaves the source volumes untouched as rollback assets:

```powershell
.\scripts\migrate-docker-storage.ps1 -DataRoot "D:\Cookfully"
```

Set the same `COOKFULLY_DATA_ROOT=D:/Cookfully` in `deploy/.env`, start the stack, and verify a
recipe, photo, and backup status before considering the old volumes for removal. A volume that was
already deleted cannot be recovered by this script; restore it only from a pre-existing backup.

## Troubleshooting

**`Set POSTGRES_PASSWORD in .env` (or another `Set X in .env` error)** — `deploy/.env` is missing or
does not contain the named variable. Copy `deploy/.env.example` to `deploy/.env` and fill in the
three required values, then retry.

**`port is already allocated` for 5432 / 6379 / 8080** — another PostgreSQL, Redis, or web server
already uses the port. Stop the conflicting process, or remap the ports with a Compose override file
(for example `ports: ["15432:5432"]`) and adjust `COOKFULLY_PUBLIC_BASE_URL`/`COOKFULLY_API_BASE_URL`
to the web port you chose.

**`api` never becomes healthy** — check the logs for the real cause:

```bash
docker compose -f deploy/compose.yaml logs --tail 100 api
```

Common causes: an old `cookfully-*` container set occupying the ports (remove it with
`docker compose -p <old-project-name> down`), or a database folder created with different
credentials (rare; point `COOKFULLY_DATA_ROOT` to a new empty folder only if you are evaluating a
fresh kitchen).

**Login fails** — the owner account is created at the API's first startup with
`COOKFULLY_OWNER_EMAIL` and `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD`. If you change these after the
first start, the database keeps the original values; use a new empty `COOKFULLY_DATA_ROOT` only when
you intentionally want a new kitchen.

**Importing a recipe URL hangs or fails** — the site may block automated access. Cookfully shows a
recovery path: paste the recipe text instead.
