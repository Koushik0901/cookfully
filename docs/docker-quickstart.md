# Docker quickstart: run Cookfully on your machine

The fastest way to try Cookfully is the full Docker Compose stack. It builds and runs the web
client, API, workers, PostgreSQL, and Redis with one command. No Node, Python, or `uv` install is
needed — only Docker.

For the development workflow (live-reloading API and client, tests, CLI tools), use the
[development quickstart](../specs/001-nutrition-recipe-planner/quickstart.md) instead. For a
production deployment with TLS and a reverse proxy, see [self-hosting](self-hosting.md).

## Prerequisites

- Git
- Docker Engine with the Compose v2 plugin, or Docker Desktop
- ~4 GB free RAM and ~10 GB free disk (first build pulls images and installs dependencies)

## 1. Clone the repository

```bash
git clone https://github.com/Koushik0901/cookfully.git
cd cookfully
```

## 2. Create the environment file

Compose fails closed without secrets: it refuses to start until `deploy/.env` exists with the three
required values. Copy the template and fill them in.

```powershell
Copy-Item -LiteralPath 'deploy\.env.example' -Destination 'deploy\.env'
```

Open `deploy/.env` and replace the three required placeholders:

| Variable | Purpose | Example value |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | Database password | `ChangeMe-Database-2026` |
| `COOKFULLY_SECRET_KEY` | Session signing / diagnostics key, 32+ chars | `openssl rand -hex 32` output |
| `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD` | Sign-in password for the single owner account | `ChangeMe-Owner-2026!` |

The owner email defaults to `owner@example.com`; set `COOKFULLY_OWNER_EMAIL` in the same file to
change it. Everything else already has a working local default.

> `.env` is gitignored. Never commit it.

## 3. Build and start the stack

From the repository root:

```bash
docker compose -f deploy/compose.yaml up -d --build
```

The first build takes a few minutes (it installs locked frontend dependencies and the Python
environment). It starts seven services: `web`, `api`, `worker`, `outbox`, `retention`, `postgres`,
and `redis`. The API runs database migrations automatically on first start and creates the owner
account from `COOKFULLY_OWNER_*`.

Check that everything is healthy:

```bash
docker compose -f deploy/compose.yaml ps
```

Wait until `api`, `postgres`, `redis`, `web`, and `retention` report `healthy`.

## 4. Open the app

Visit <http://localhost:8080> and sign in with:

- Email: the value of `COOKFULLY_OWNER_EMAIL` (default `owner@example.com`)
- Password: the value of `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD`

The API health endpoint is at <http://localhost:8080/api/v1/health>; the OpenAPI document is at
<http://localhost:8080/api/openapi.json>.

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

## Rebuilding after a code change

Frontend and backend images are built from the repository, so pull new commits and rebuild the
affected image:

```bash
git pull
docker compose -f deploy/compose.yaml up -d --build
```

To rebuild only the web client (fastest loop): `docker compose -f deploy/compose.yaml up -d --build web`.

## Stopping and removing

```bash
# Stop everything (data is kept in named volumes)
docker compose -f deploy/compose.yaml down

# Stop and delete all data (recipes, plans, owner account, media)
docker compose -f deploy/compose.yaml down -v
```

`down -v` is destructive — there is no undo. Backups can be created and verified with the CLI, see
[docs/backup-restore.md](backup-restore.md).

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
`docker compose -p <old-project-name> down`), or a database volume created with different
credentials (rare; `down -v` and restart if you are only evaluating).

**Login fails** — the owner account is created at the API's first startup with
`COOKFULLY_OWNER_EMAIL` and `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD`. If you change these after the
first start, the database keeps the original values; wipe the stack (`down -v`) to re-bootstrap.

**Importing a recipe URL hangs or fails** — the site may block automated access. Cookfully shows a
recovery path: paste the recipe text instead.