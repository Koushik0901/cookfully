# Secure deployment: ZimaOS + Tailscale

Goal: Cookfully runs as Docker containers on a ZimaOS server and is reachable only from your own
devices over Tailscale, with HTTPS end to end from the browser to the server.

## 1. Configure

```bash
cd deploy
cp .env.example .env
# Fill every secret with a random value:
openssl rand -base64 24   # POSTGRES_PASSWORD
openssl rand -hex 32      # COOKFULLY_SECRET_KEY, COOKFULLY_INTELLIGENCE_SERVICE_KEY
python3 -c "import uuid; print(uuid.uuid4())"   # COOKFULLY_INSTANCE_ID
chmod 600 .env
```

Uncomment the "Remote access over Tailscale" block in `.env` and set both URLs to your machine's
MagicDNS name (for example `https://cookfully.your-tailnet.ts.net`). Start with the production
overlay, which refuses to boot with a weak or default setting:

```bash
docker compose -f compose.yaml -f compose.production.yaml up -d
```

The overlay publishes the web port on `127.0.0.1` only, publishes no database or Redis port, runs
every service with `no-new-privileges` (app services also drop all Linux capabilities), keeps the
model service on an internal network with no internet, and turns off the API docs and schema.

## 2. Expose it to your tailnet with HTTPS

In the Tailscale admin console enable **MagicDNS** and **HTTPS Certificates**, then on the ZimaOS
host:

```bash
tailscale serve --bg http://127.0.0.1:8080
```

Use `serve`, **never** `funnel` (funnel publishes the app to the whole internet). `serve` terminates
TLS with a real certificate and forwards `X-Forwarded-Proto: https`, which turns on HSTS;
`COOKFULLY_COOKIE_SECURE=true` (enforced by the production overlay) makes the session cookie HTTPS-only. If Tailscale runs in its own container rather than on the host, it must share the host
network (or otherwise be able to reach `127.0.0.1:8080`).

Do not port-forward the web port on your router, and keep ZimaOS's own web UI off the internet.

## 3. Lock down who can reach it

Add a Tailscale ACL so only your own devices can open the port, for example:

```json
{"acls": [{"action": "accept", "src": ["autogroup:member"], "dst": ["tag:server:443"]}],
 "tagOwners": {"tag:server": ["autogroup:admin"]}}
```

and tag the ZimaOS node `tag:server`. Enable device approval and key expiry for the tailnet, and
turn on two-factor authentication for the identity provider behind it.

## What the app itself enforces

| Control | Where |
|---|---|
| Passwords hashed with Argon2; sessions are random, stored hashed, revocable in Settings | `application/auth.py` |
| Failed sign-ins lock out progressively (5 free tries, then 30 s doubling to 5 min), per client and globally; also covers password change | `application/login_throttle.py` |
| `HttpOnly`, `Secure`, `SameSite=Lax` session cookie plus a CSRF token on every write | `api/routes/auth.py` |
| HTTPS-only URLs, `Secure` cookies, strong unique secrets and a changed bootstrap password required in production | `infrastructure/config.py` |
| CSP, HSTS (over HTTPS), `nosniff`, no framing, no referrer, locked-down permissions policy | `deploy/docker/nginx*.conf`, `api/security_headers.py` |
| API responses are `Cache-Control: no-store`; the service worker never caches `/api/` | `api/security_headers.py`, `frontend/public/sw.js` |
| OpenRouter key encrypted at rest, write-only over the API | `infrastructure/secret_box.py` |
| Model service rejects every request without its key (constant-time check, fails closed if unset) | `intelligence/service.py` |

## Secrets and backups

- `.env` holds every secret. Keep it `chmod 600`, out of git, and back it up separately from the data.
- The OpenRouter key is encrypted with a key derived from `COOKFULLY_SECRET_KEY`. Backups of the
  database are useless without that secret, and a database backup restored under a different secret
  shows "No key saved" until you re-enter the key. Treat the secret as part of the backup.
- `COOKFULLY_OWNER_BOOTSTRAP_PASSWORD` is only used to create the first account. After the first
  sign-in, change the password under Settings → Security; the value left in `.env` is no longer used.
- Rotate `POSTGRES_PASSWORD` by changing it in Postgres first, then `.env`.

## Known limits

- Login throttling is held in memory, so it resets when the API container restarts.
- The web container still runs nginx's master process as root and the data containers (Postgres,
  Redis) are not capability-dropped; these were not changed because they could not be run and tested
  in the build environment.
- Anyone who can already sign in to your tailnet *and* passes the ACL can reach the login page; the
  app's password and throttle are the second layer, not the only one.
