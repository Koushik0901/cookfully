# Cookfully intelligence model

The `intelligence` Compose service is the model boundary. It is intentionally
not given database or Redis credentials; the Cookfully API and existing worker
remain responsible for authentication, coordination, persistence, retries, and
execution.

Compose places the service on a private `intelligence-net` shared only with the
API and worker. Postgres and Redis are not attached to that network.

Needle2 is enabled by default. The local service starts automatically, but the
release image does not ship model weights. To make inference ready, place the
pinned Needle 2 artifact at
`<COOKFULLY_DATA_ROOT>/intelligence-models/needle2.cact`. Obtain it from the
approved model release and verify its release checksum. If the artifact is
missing, the service reports `degraded` and Cookfully safely falls back to its
deterministic paths. Do not mount application media or database directories into
this service.

The owner can turn Needle2 and its inline import/repair assistance off or back
on under **Settings → Intelligence**. The `COOKFULLY_INTELLIGENCE_ENABLED` and
`COOKFULLY_INTELLIGENCE_INLINE_ENABLED` environment variables remain emergency
operator kill switches; both default to `true`.

For a remote model host, set `COOKFULLY_INTELLIGENCE_URL` on the API and worker
to an HTTPS endpoint and configure the same service key on both sides. Keep the
model host on a trusted private network; it is not a public API.
