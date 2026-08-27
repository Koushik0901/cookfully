#!/bin/sh
set -eu

backup_root="${COOKFULLY_BACKUP_ROOT:-/data/backups}"
database_root="$backup_root/database"
requests_root="$backup_root/requests"
status_path="$backup_root/status.json"
heartbeat_path="$backup_root/.heartbeat"
schedule="${COOKFULLY_DATABASE_BACKUP_SCHEDULE:-02:00}"
retention_count="${COOKFULLY_DATABASE_BACKUP_RETENTION_COUNT:-14}"

case "$schedule" in
  [01][0-9]:[0-5][0-9]|2[0-3]:[0-5][0-9]) ;;
  *) echo "COOKFULLY_DATABASE_BACKUP_SCHEDULE must use HH:MM (24-hour)" >&2; exit 64 ;;
esac

case "$retention_count" in
  ''|*[!0-9]*) echo "COOKFULLY_DATABASE_BACKUP_RETENTION_COUNT must be a positive integer" >&2; exit 64 ;;
esac

if [ "$retention_count" -lt 1 ]; then
  echo "COOKFULLY_DATABASE_BACKUP_RETENTION_COUNT must be at least 1" >&2
  exit 64
fi

mkdir -p "$database_root" "$requests_root"

utc_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

write_status() {
  last_success_at="$1"
  failure_at="$2"
  failure_message="$3"
  heartbeat_at="$(utc_now)"
  tmp_path="$status_path.partial"
  if [ -n "$last_success_at" ]; then
    last_success_json="\"$last_success_at\""
  else
    last_success_json="null"
  fi
  if [ -n "$failure_at" ]; then
    escaped_message=$(printf '%s' "$failure_message" | tr '\n' ' ' | sed 's/"/\\\\"/g')
    printf '{"heartbeatAt":"%s","lastFailure":{"message":"%s","occurredAt":"%s"},"lastSuccessAt":%s}\n' \
      "$heartbeat_at" "$escaped_message" "$failure_at" "$last_success_json" > "$tmp_path"
  else
    printf '{"heartbeatAt":"%s","lastFailure":null,"lastSuccessAt":%s}\n' \
      "$heartbeat_at" "$last_success_json" > "$tmp_path"
  fi
  mv "$tmp_path" "$status_path"
  printf '%s\n' "$heartbeat_at" > "$heartbeat_path"
}

latest_success_at() {
  if [ ! -f "$status_path" ]; then
    return 0
  fi
  sed -n 's/.*"lastSuccessAt":"\([^"]*\)".*/\1/p' "$status_path" | head -n 1
}

acquire_lock() {
  lock_path="$backup_root/.database-backup.lock"
  if ! mkdir "$lock_path" 2>/dev/null; then
    return 1
  fi
  return 0
}

release_lock() {
  rmdir "$backup_root/.database-backup.lock" 2>/dev/null || true
}

prune_backups() {
  number=0
  for dump_path in $(ls -1t "$database_root"/*.dump 2>/dev/null || true); do
    number=$((number + 1))
    if [ "$number" -gt "$retention_count" ]; then
      stem=${dump_path%.dump}
      rm -f "$dump_path" "$stem.json" "$dump_path.sha256"
    fi
  done
}

backup_once() {
  reason="$1"
  if ! acquire_lock; then
    return 75
  fi
  started_at="$(utc_now)"
  stem="cookfully-postgres-$(date -u +%Y%m%dT%H%M%SZ)"
  dump_path="$database_root/$stem.dump"
  partial_path="$dump_path.partial"
  manifest_path="$database_root/$stem.json"
  checksum_path="$dump_path.sha256"
  if ! pg_dump --format=custom --no-owner --no-privileges --file="$partial_path"; then
    rm -f "$partial_path"
    write_status "$(latest_success_at)" "$(utc_now)" "pg_dump failed"
    release_lock
    return 1
  fi
  mv "$partial_path" "$dump_path"
  checksum=$(sha256sum "$dump_path" | awk '{print $1}')
  bytes=$(wc -c < "$dump_path" | tr -d ' ')
  completed_at="$(utc_now)"
  printf '%s  %s\n' "$checksum" "$(basename "$dump_path")" > "$checksum_path.partial"
  mv "$checksum_path.partial" "$checksum_path"
  printf '{"bytes":%s,"createdAt":"%s","filename":"%s","reason":"%s","sha256":"%s","startedAt":"%s"}\n' \
    "$bytes" "$completed_at" "$(basename "$dump_path")" "$reason" "$checksum" "$started_at" > "$manifest_path.partial"
  mv "$manifest_path.partial" "$manifest_path"
  prune_backups
  write_status "$completed_at" "" ""
  release_lock
}

run_pending_requests() {
  for request_path in "$requests_root"/*.json; do
    [ -e "$request_path" ] || continue
    if backup_once manual; then
      rm -f "$request_path"
    fi
    return
  done
}

is_scheduled_now() {
  [ "$(date +%H:%M)" = "$schedule" ] && [ "$(date +%S)" -lt 30 ]
}

serve() {
  last_scheduled_day=""
  while :; do
    printf '%s\n' "$(utc_now)" > "$heartbeat_path"
    run_pending_requests
    today="$(date +%F)"
    if is_scheduled_now && [ "$last_scheduled_day" != "$today" ]; then
      backup_once schedule || true
      last_scheduled_day="$today"
    fi
    sleep 20
  done
}

healthcheck() {
  [ -s "$heartbeat_path" ] || exit 1
  last_heartbeat=$(cat "$heartbeat_path")
  last_epoch=$(date -d "$last_heartbeat" +%s 2>/dev/null || echo 0)
  now_epoch=$(date +%s)
  [ $((now_epoch - last_epoch)) -lt 130 ]
}

case "${1:-serve}" in
  serve) serve ;;
  run) backup_once host-copy ;;
  healthcheck) healthcheck ;;
  *) echo "Usage: cookfully-database-backup [serve|run|healthcheck]" >&2; exit 64 ;;
esac
