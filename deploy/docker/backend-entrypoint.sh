#!/bin/sh
set -eu

if [ "${COOKFULLY_RUN_MIGRATIONS:-false}" = "true" ]; then
  alembic upgrade head
fi

exec "$@"
