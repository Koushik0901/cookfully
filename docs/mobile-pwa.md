# Mobile and PWA deployment

Cookfully is a self-hosted web app. The server owns the database, media, jobs, and backups; a phone
is a client that can install the web app from Safari or Chrome. A native app is not required.

## Choose how the phone reaches the server

### Trusted home LAN

For a quick household setup, open Cookfully from the server's LAN address, for example
`http://192.168.1.20:8080`. `localhost` only refers to the device that is currently opening the
browser. Keep this mode on a trusted network and do not forward port 8080 to the public internet.

For a long-lived installation, use HTTPS even on the LAN with a local reverse proxy and set:

```dotenv
COOKFULLY_PUBLIC_BASE_URL=https://recipes.home.example
COOKFULLY_API_BASE_URL=https://recipes.home.example
COOKFULLY_COOKIE_SECURE=true
```

### Optional Tailscale access

Tailscale is an optional transport between the phone and the user's server. Install Tailscale on
the host and phone, enable MagicDNS, and expose the local Cookfully web gateway through the host's
Tailscale address or a Tailscale Serve/reverse-proxy rule. Use the HTTPS MagicDNS name as the
Cookfully base URL:

```dotenv
COOKFULLY_PUBLIC_BASE_URL=https://cookfully.<tailnet-name>.ts.net
COOKFULLY_API_BASE_URL=https://cookfully.<tailnet-name>.ts.net
COOKFULLY_COOKIE_SECURE=true
```

The production Compose profile intentionally binds the web gateway to `127.0.0.1:8080`; a host-level
Tailscale Serve rule or reverse proxy can reach it without publishing PostgreSQL or Redis. Keep
Tailscale ACLs limited to the household, and do not enable a public Funnel unless public access is
an explicit, separately reviewed requirement. Tailscale is not required: a LAN hostname or another
HTTPS reverse proxy remains a supported path.

## Install on a phone

1. Open the configured HTTPS URL while signed in.
2. iPhone/iPad: Safari → Share → **Add to Home Screen**.
3. Android: Chrome → menu → **Install app** (or **Add to home screen**).
4. Open the new Cookfully icon. The app keeps the cooking shell, safe-area navigation, and Cook Mode
   available as a standalone web app.

Cookfully caches the application shell and recently viewed JSON reads. Cook Mode shows **Available
offline** only after its recipe has been persisted on the device. If the connection drops, the phone
shows an offline banner and can continue reading cached recipes and Cook Mode content. Writes remain
explicitly connected operations and expose a retry path; the server remains authoritative.
When the application shell changes, bump the cache version in `frontend/public/sw.js`; the deployment
revalidates that worker and rolls the shell cache so installed phones can pick up the new build without
clearing browser storage.

## Release acceptance on real devices

- iPhone SE and a current iPhone on Safari.
- A small Android phone on Chrome.
- Sign-in, reload, sign-out, and session restoration over LAN and Tailscale MagicDNS.
- Recipe read, Cook Mode step persistence, timer, wake-lock fallback, photo upload, and PDF URL import.
- Background the browser, lock the screen, restore the connection, and confirm job progress resumes.
- Portrait/landscape, safe-area insets, virtual keyboard, 200% text zoom, VoiceOver/TalkBack, and no
  horizontal overflow.
- Install, update, and offline-shell behavior after a new deployment.
- Restore a verified database/media backup before declaring the host ready for users.
