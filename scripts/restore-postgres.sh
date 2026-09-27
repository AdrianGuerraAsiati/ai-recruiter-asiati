#!/usr/bin/env bash
# Restore a PostgreSQL custom-format backup. Destructive by design and guarded.
set -euo pipefail

DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_FILE="${1:?usage: restore-postgres.sh /path/to/backup.dump}"
CONFIRM_RESTORE="${CONFIRM_RESTORE:-}"

if [[ "$CONFIRM_RESTORE" != "yes" ]]; then
  echo "Refusing restore. Set CONFIRM_RESTORE=yes after validating the target database." >&2
  exit 2
fi

command -v pg_restore >/dev/null 2>&1 || {
  echo "pg_restore is required" >&2
  exit 1
}

test -s "$BACKUP_FILE"
if [[ -f "$BACKUP_FILE.sha256" ]]; then
  (cd "$(dirname "$BACKUP_FILE")" && sha256sum -c "$(basename "$BACKUP_FILE").sha256")
fi

RESTORE_DATABASE_URL="${DATABASE_URL/host.docker.internal/127.0.0.1}"

pg_restore   --dbname="$RESTORE_DATABASE_URL"   --clean   --if-exists   --no-owner   --no-privileges   "$BACKUP_FILE"

echo "DATABASE_RESTORE_OK"
