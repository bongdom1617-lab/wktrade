#!/usr/bin/env bash
set -euo pipefail

AGENTS_DIR="$HOME/Library/LaunchAgents"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
launchctl unload "$AGENTS_DIR/com.goldai.tunnel.plist" 2>/dev/null || true
launchctl unload "$AGENTS_DIR/com.goldai.gateway.plist" 2>/dev/null || true
rm -f "$AGENTS_DIR/com.goldai.tunnel.plist" "$AGENTS_DIR/com.goldai.gateway.plist" "$ROOT_DIR/bin/run-named-tunnel.sh"

echo "GOLD AI Cloudflare Tunnel and local gateway stopped and removed."
