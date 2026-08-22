#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-$ROOT_DIR/deploy/docker-compose.staging.yml}
ENV_FILE=${ENV_FILE:-$ROOT_DIR/deploy/.env.staging}
BACKUP_FILE=${1:-}

[ -f "$COMPOSE_FILE" ] || { echo "Compose file not found: $COMPOSE_FILE" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Environment file not found: $ENV_FILE" >&2; exit 1; }
[ -n "$BACKUP_FILE" ] || { echo "Usage: $0 /path/to/pdv-YYYYmmddTHHMMSSZ.dump" >&2; exit 1; }
[ -f "$BACKUP_FILE" ] || { echo "Backup file not found: $BACKUP_FILE" >&2; exit 1; }
[ "${CONFIRM_RESTORE:-}" = "YES" ] || {
  echo "Restore is destructive. Set CONFIRM_RESTORE=YES to continue." >&2
  exit 1
}

echo "Stopping application services before restore..."
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop backend frontend proxy

restart_services() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d backend frontend proxy
}
trap restart_services EXIT

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore --clean --if-exists --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  < "$BACKUP_FILE"

echo "Database restored from: $BACKUP_FILE"
