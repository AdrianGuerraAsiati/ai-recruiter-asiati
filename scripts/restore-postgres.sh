#!/usr/bin/env bash
# Restore a PostgreSQL custom-format backup. Destructive by design and guarded.
set -euo pipefail

DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_SOURCE="${1:?usage: restore-postgres.sh /path/to/backup.dump|s3://bucket/key.dump}"
CONFIRM_RESTORE="${CONFIRM_RESTORE:-}"
BACKUP_AWS_PROFILE="${BACKUP_AWS_PROFILE:-}"
BACKUP_AWS_CONFIG_FILE="${BACKUP_AWS_CONFIG_FILE:-}"

if [[ "$CONFIRM_RESTORE" != "yes" ]]; then
  echo "Refusing restore. Set CONFIRM_RESTORE=yes after validating the target database." >&2
  exit 2
fi

command -v pg_restore >/dev/null 2>&1 || {
  echo "pg_restore is required" >&2
  exit 1
}

TEMP_DIR=""
cleanup() {
  if [[ -n "$TEMP_DIR" ]]; then
    rm -rf "$TEMP_DIR"
  fi
}
trap cleanup EXIT

BACKUP_FILE="$BACKUP_SOURCE"
if [[ "$BACKUP_SOURCE" == s3://* ]]; then
  command -v aws >/dev/null 2>&1 || {
    echo "aws CLI is required to restore from S3" >&2
    exit 1
  }

  AWS_ARGS=()
  if [[ -n "$BACKUP_AWS_PROFILE" ]]; then
    AWS_ARGS+=(--profile "$BACKUP_AWS_PROFILE")
  fi

  AWS_ENV=()
  if [[ -n "$BACKUP_AWS_CONFIG_FILE" ]]; then
    AWS_ENV+=(AWS_CONFIG_FILE="$BACKUP_AWS_CONFIG_FILE")
  fi

  TEMP_DIR=$(mktemp -d)
  BACKUP_FILE="$TEMP_DIR/$(basename "$BACKUP_SOURCE")"
  env "${AWS_ENV[@]}" aws "${AWS_ARGS[@]}" s3 cp "$BACKUP_SOURCE" "$BACKUP_FILE" --only-show-errors
  env "${AWS_ENV[@]}" aws "${AWS_ARGS[@]}" s3 cp "$BACKUP_SOURCE.sha256" "$BACKUP_FILE.sha256" --only-show-errors
fi

test -s "$BACKUP_FILE"
test -s "$BACKUP_FILE.sha256"
(
  cd "$(dirname "$BACKUP_FILE")"
  sha256sum -c "$(basename "$BACKUP_FILE").sha256"
)

RESTORE_DATABASE_URL="${DATABASE_URL/host.docker.internal/127.0.0.1}"

pg_restore \
  --dbname="$RESTORE_DATABASE_URL" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  "$BACKUP_FILE"

echo "DATABASE_RESTORE_OK"
