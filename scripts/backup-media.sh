#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
MEDIA_VOLUME=${MEDIA_VOLUME:-deploy_media_data}
BACKUP_DIR=${BACKUP_DIR:-$ROOT_DIR/backups}
RETENTION_DAYS=${RETENTION_DAYS:-14}

case "$RETENTION_DAYS" in
  ''|*[!0-9]*) echo "RETENTION_DAYS must be a non-negative integer" >&2; exit 1 ;;
esac

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_file="$BACKUP_DIR/pdv-media-$timestamp.tar.gz"
temporary_file="$backup_file.tmp"

cleanup() {
  rm -f "$temporary_file"
}
trap cleanup EXIT

docker run --rm \
  -v "$MEDIA_VOLUME:/media:ro" \
  -v "$BACKUP_DIR:/backups" \
  alpine:3.20 \
  tar -czf "/backups/$(basename "$temporary_file")" -C /media .

test -s "$temporary_file"
mv "$temporary_file" "$backup_file"
chmod 600 "$backup_file"

find "$BACKUP_DIR" -type f -name 'pdv-media-*.tar.gz' -mtime "+$RETENTION_DAYS" -delete
echo "Media backup created: $backup_file"
