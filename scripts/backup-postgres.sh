#!/usr/bin/env bash
# Create a permission-restricted PostgreSQL backup before production migrations.
set -euo pipefail

DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-/opt/ai-recruiter/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

command -v pg_dump >/dev/null 2>&1 || {
  echo "pg_dump is required" >&2
  exit 1
}

umask 077
mkdir -p "$BACKUP_DIR"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTPUT="$BACKUP_DIR/ai-recruiter-${STAMP}.dump"

pg_dump   --dbname="$DATABASE_URL"   --format=custom   --no-owner   --no-privileges   --file="$OUTPUT"

test -s "$OUTPUT"
sha256sum "$OUTPUT" > "$OUTPUT.sha256"

find "$BACKUP_DIR" -type f -name 'ai-recruiter-*.dump' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'ai-recruiter-*.dump.sha256' -mtime "+$RETENTION_DAYS" -delete

echo "DATABASE_BACKUP_OK=$OUTPUT"
