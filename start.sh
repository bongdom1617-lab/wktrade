#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

# Build frontend production bundle automatically if missing
if [ ! -d "$ROOT_DIR/frontend/.next" ]; then
  echo "Building GOLD AI Frontend production bundle..."
  (cd "$ROOT_DIR/frontend" && npm run build)
fi

supervise() {
  local name="$1"
  shift
  while true; do
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Starting $name..."
    "$@" || true
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $name exited — restarting in 3s..."
    sleep 3
  done
}

echo "Starting GOLD AI Self-Healing Services..."
echo "  Dashboard: http://localhost:3000"
echo "  API Docs : http://127.0.0.1:8000/docs"
echo "  Logs     : $LOG_DIR"

supervise "GOLD AI Backend" \
  "$ROOT_DIR/backend/.venv/bin/uvicorn" app.main:app \
  --app-dir "$ROOT_DIR/backend" --host 127.0.0.1 --port 8000 \
  >> "$LOG_DIR/backend.log" 2>&1 &
BACK_PID=$!

supervise "GOLD AI Frontend" \
  npm run start --prefix "$ROOT_DIR/frontend" \
  >> "$LOG_DIR/frontend.log" 2>&1 &
FRONT_PID=$!

cleanup() {
  echo "Stopping GOLD AI services..."
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
  pkill -P "$BACK_PID" 2>/dev/null || true
  pkill -P "$FRONT_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

wait
