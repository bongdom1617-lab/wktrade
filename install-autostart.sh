#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$AGENTS_DIR" "$LOG_DIR"

NODE_BIN_DIR="$(dirname "$(which node)")"
PATH_ENV="$NODE_BIN_DIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Ensure production Next.js build exists at repo root
if [ ! -d "$ROOT_DIR/.next" ]; then
  echo "Building GOLD AI Next.js production bundle..."
  (cd "$ROOT_DIR" && npm run build)
fi

cat > "$AGENTS_DIR/com.goldai.backend.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.goldai.backend</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ROOT_DIR/backend/.venv/bin/uvicorn</string>
    <string>app.main:app</string>
    <string>--app-dir</string><string>$ROOT_DIR/backend</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8000</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT_DIR/backend</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$PATH_ENV</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/backend.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/backend.err.log</string>
</dict>
</plist>
EOF

cat > "$AGENTS_DIR/com.goldai.frontend.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.goldai.frontend</string>
  <key>ProgramArguments</key>
  <array>
    <string>$NODE_BIN_DIR/npm</string>
    <string>run</string>
    <string>start</string>
    <string>--prefix</string><string>$ROOT_DIR</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT_DIR</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$PATH_ENV</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/frontend.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/frontend.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$AGENTS_DIR/com.goldai.backend.plist" 2>/dev/null || true
launchctl unload "$AGENTS_DIR/com.goldai.frontend.plist" 2>/dev/null || true

pkill -f "gold-ai/backend.*uvicorn" 2>/dev/null || true
pkill -f "gold-ai.*next" 2>/dev/null || true
sleep 1

launchctl load "$AGENTS_DIR/com.goldai.backend.plist"
launchctl load "$AGENTS_DIR/com.goldai.frontend.plist"
sleep 2

echo "GOLD AI autostart installed and running!"
echo "  Dashboard: http://localhost:3000"
echo "  Backend  : http://127.0.0.1:8000/docs"
echo "  Logs     : $LOG_DIR"
