#!/bin/sh
set -eu

backup_root="${COOKFULLY_BACKUP_ROOT:-/data/backups}"
mkdir -p "$backup_root/database" "$backup_root/requests"
chown -R 999:999 "$backup_root"
chmod 0750 "$backup_root" "$backup_root/database" "$backup_root/requests"

exec gosu 999:999 cookfully-database-backup "$@"
