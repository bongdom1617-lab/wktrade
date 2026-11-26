#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
URL="$(grep -hEo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$ROOT_DIR/logs/tunnel.err.log" "$ROOT_DIR/logs/tunnel.log" 2>/dev/null | tail -n 1 || true)"
if [ -n "$URL" ]; then
  echo "$URL"
else
  echo "No active Quick Tunnel URL found yet. Check $ROOT_DIR/logs/tunnel.err.log" >&2
  exit 1
fi
