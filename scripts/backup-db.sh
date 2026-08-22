#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-$ROOT_DIR/deploy/docker-compose.staging.yml}
ENV_FILE=${ENV_FILE:-$ROOT_DIR/deploy/.env.staging}
BACKUP_DIR=${BACKUP_DIR:-$ROOT_DIR/backups}
RETENTION_DAYS=${RETENTION_DAYS:-14}

[ -f "$COMPOSE_FILE" ] || { echo "Compose file not found: $COMPOSE_FILE" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Environment file not found: $ENV_FILE" >&2; exit 1; }

case "$RETENTION_DAYS" in
  ''|*[!0-9]*) echo "RETENTION_DAYS must be a non-negative integer" >&2; exit 1 ;;
esac

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_file="$BACKUP_DIR/pdv-$timestamp.dump"
temporary_file="$backup_file.tmp"

cleanup() {
  rm -f "$temporary_file"
}
trap cleanup EXIT

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --format=custom --no-owner --no-acl --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  > "$temporary_file"

test -s "$temporary_file"
mv "$temporary_file" "$backup_file"
chmod 600 "$backup_file"

find "$BACKUP_DIR" -type f -name 'pdv-*.dump' -mtime "+$RETENTION_DAYS" -delete
echo "Backup created: $backup_file"
