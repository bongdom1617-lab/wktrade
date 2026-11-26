#!/usr/bin/env bash
set -euo pipefail

AGENTS_DIR="$HOME/Library/LaunchAgents"
launchctl unload "$AGENTS_DIR/com.goldai.backend.plist" 2>/dev/null || true
launchctl unload "$AGENTS_DIR/com.goldai.frontend.plist" 2>/dev/null || true
rm -f "$AGENTS_DIR/com.goldai.backend.plist" "$AGENTS_DIR/com.goldai.frontend.plist"

echo "GOLD AI macOS autostart services stopped and removed."
