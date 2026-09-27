#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="${FRONTEND_DIR:-frontend-react}"
PORT="${FRONTEND_E2E_PORT:-4173}"
BASE_URL="http://127.0.0.1:${PORT}"
LOG_FILE="${RUNNER_TEMP:-/tmp}/ai-recruiter-vite-preview.log"

cleanup() {
  if [[ -n "${PREVIEW_PID:-}" ]]; then
    kill "$PREVIEW_PID" >/dev/null 2>&1 || true
    wait "$PREVIEW_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

(
  cd "$FRONTEND_DIR"
  npm run preview -- --host 127.0.0.1 --port "$PORT"
) >"$LOG_FILE" 2>&1 &
PREVIEW_PID=$!

READY=false
for _ in $(seq 1 30); do
  if curl -fsS "$BASE_URL/login" >/dev/null; then
    READY=true
    break
  fi
  sleep 1
done

if [[ "$READY" != "true" ]]; then
  cat "$LOG_FILE" >&2 || true
  exit 1
fi

FRONTEND_E2E_BASE_URL="$BASE_URL" python -m pytest -q "$FRONTEND_DIR/e2e"
