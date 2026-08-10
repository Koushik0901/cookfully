#!/bin/sh
set -eu

if [ "${VV_RUN_MIGRATIONS:-false}" = "true" ]; then
  alembic upgrade head
fi

exec "$@"
