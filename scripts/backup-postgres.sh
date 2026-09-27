#!/usr/bin/env bash
# Create a permission-restricted PostgreSQL backup before production migrations.
set -euo pipefail

DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-/opt/ai-recruiter/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
BACKUP_S3_URI="${BACKUP_S3_URI:-}"
BACKUP_AWS_PROFILE="${BACKUP_AWS_PROFILE:-}"

command -v pg_dump >/dev/null 2>&1 || {
  echo "pg_dump is required" >&2
  exit 1
}

umask 077
mkdir -p "$BACKUP_DIR"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUTPUT="$BACKUP_DIR/ai-recruiter-${STAMP}.dump"

# The application containers reach host PostgreSQL through host.docker.internal.
# This backup runs on the host itself, where that Docker-only hostname is not
# resolvable; normalize only that host alias and preserve the rest of the DSN.
BACKUP_DATABASE_URL="${DATABASE_URL/host.docker.internal/127.0.0.1}"

pg_dump   --dbname="$BACKUP_DATABASE_URL"   --format=custom   --no-owner   --no-privileges   --file="$OUTPUT"

test -s "$OUTPUT"
sha256sum "$OUTPUT" > "$OUTPUT.sha256"

if [[ -n "$BACKUP_S3_URI" ]]; then
  command -v aws >/dev/null 2>&1 || {
    echo "aws CLI is required when BACKUP_S3_URI is configured" >&2
    exit 1
  }

  AWS_ARGS=()
  if [[ -n "$BACKUP_AWS_PROFILE" ]]; then
    AWS_ARGS+=(--profile "$BACKUP_AWS_PROFILE")
  fi

  DESTINATION="${BACKUP_S3_URI%/}/$(basename "$OUTPUT")"
  aws "${AWS_ARGS[@]}" s3 cp "$OUTPUT" "$DESTINATION" --only-show-errors --sse AES256
  aws "${AWS_ARGS[@]}" s3 cp "$OUTPUT.sha256" "$DESTINATION.sha256" --only-show-errors --sse AES256
  echo "DATABASE_BACKUP_OFFHOST_OK=$DESTINATION"
fi

find "$BACKUP_DIR" -type f -name 'ai-recruiter-*.dump' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -type f -name 'ai-recruiter-*.dump.sha256' -mtime "+$RETENTION_DAYS" -delete

echo "DATABASE_BACKUP_OK=$OUTPUT"
