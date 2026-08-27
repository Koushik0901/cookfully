# Cookfully intelligence model

The `intelligence` Compose service is the model boundary. It is intentionally
not given database or Redis credentials; the Cookfully API and existing worker
remain responsible for authentication, coordination, persistence, retries, and
execution.

Compose places the service on a private `intelligence-net` shared only with the
API and worker. Postgres and Redis are not attached to that network.

Place the pinned Needle 2 model artifact at
`<COOKFULLY_DATA_ROOT>/intelligence-models/needle2.cact` before enabling
production inference. The artifact must be obtained from the approved model
release and verified against the release checksum. Do not mount the application
media or database directories into this service.

For a remote model host, set `COOKFULLY_INTELLIGENCE_URL` on the API and worker
to an HTTPS endpoint and configure the same service key on both sides. Keep the
model host on a trusted private network; it is not a public API.
