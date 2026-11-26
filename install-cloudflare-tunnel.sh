#!/usr/bin/env bash
set -euo pipefail

# Installs and starts GOLD AI Single-Origin Gateway (:8080) + Cloudflare Tunnel via macOS launchd.
# Usage:
#   ./install-cloudflare-tunnel.sh --quick              # Free instant https://*.trycloudflare.com URL (no account needed)
#   ./install-cloudflare-tunnel.sh <CLOUDFLARE_TOKEN>   # Permanent named tunnel from Cloudflare Zero Trust dashboard

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT_DIR/logs"
BIN_DIR="$ROOT_DIR/bin"
CF_BIN="$BIN_DIR/cloudflared"
mkdir -p "$AGENTS_DIR" "$LOG_DIR" "$BIN_DIR"

MODE="${1:-}"
if [ -z "$MODE" ]; then
  echo "Usage:"
  echo "  $0 --quick                # Instant free Quick Tunnel (no Cloudflare account required)"
  echo "  $0 <TUNNEL_TOKEN>         # Permanent Named Tunnel using Cloudflare Zero Trust token"
  exit 1
fi

if [ ! -x "$CF_BIN" ]; then
  if command -v cloudflared >/dev/null 2>&1; then
    CF_BIN="$(command -v cloudflared)"
  else
    echo "Downloading official Cloudflare cloudflared binary for macOS..."
    ARCH="$(uname -m)"
    if [ "$ARCH" = "arm64" ]; then
      DL_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz"
    else
      DL_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz"
    fi
    curl -fsSL "$DL_URL" -o "$BIN_DIR/cloudflared.tgz"
    tar -xzf "$BIN_DIR/cloudflared.tgz" -C "$BIN_DIR"
    rm -f "$BIN_DIR/cloudflared.tgz"
    chmod +x "$CF_BIN"
  fi
fi

NODE_BIN="$(command -v node)"
NODE_BIN_DIR="$(dirname "$NODE_BIN")"
PATH_ENV="$NODE_BIN_DIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# 1. Install/Update Single-Origin Gateway LaunchAgent (:8080)
cat > "$AGENTS_DIR/com.goldai.gateway.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.goldai.gateway</string>
  <key>ProgramArguments</key>
  <array>
    <string>$NODE_BIN</string>
    <string>$ROOT_DIR/gateway/server.mjs</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$PATH_ENV</string>
    <key>GATEWAY_HOST</key><string>127.0.0.1</string>
    <key>GATEWAY_PORT</key><string>8095</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/gateway.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/gateway.err.log</string>
</dict>
</plist>
EOF

# 2. Install/Update Cloudflare Tunnel LaunchAgent
if [ "$MODE" = "--quick" ]; then
  ARGS_XML="    <string>$CF_BIN</string>
    <string>tunnel</string>
    <string>--no-autoupdate</string>
    <string>--url</string>
    <string>http://127.0.0.1:8095</string>"
else
  # Store token in a private chmod-600 launcher so token is kept secure on disk
  TOKEN_SCRIPT="$BIN_DIR/run-named-tunnel.sh"
  cat > "$TOKEN_SCRIPT" <<TEOF
#!/usr/bin/env bash
exec "$CF_BIN" tunnel --no-autoupdate run --token "$MODE"
TEOF
  chmod 700 "$TOKEN_SCRIPT"
  ARGS_XML="    <string>$TOKEN_SCRIPT</string>"
fi

cat > "$AGENTS_DIR/com.goldai.tunnel.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.goldai.tunnel</string>
  <key>ProgramArguments</key>
  <array>
$ARGS_XML
  </array>
  <key>WorkingDirectory</key><string>$ROOT_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$LOG_DIR/tunnel.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/tunnel.err.log</string>
</dict>
</plist>
EOF

# Clear old tunnel logs so quick-tunnel URL extraction always reads the fresh URL
: > "$LOG_DIR/tunnel.log"
: > "$LOG_DIR/tunnel.err.log"

launchctl unload "$AGENTS_DIR/com.goldai.gateway.plist" 2>/dev/null || true
launchctl unload "$AGENTS_DIR/com.goldai.tunnel.plist" 2>/dev/null || true
launchctl load "$AGENTS_DIR/com.goldai.gateway.plist"
launchctl load "$AGENTS_DIR/com.goldai.tunnel.plist"

echo "GOLD AI Gateway (:8095) and Cloudflare Tunnel loaded!"
if [ "$MODE" = "--quick" ]; then
  echo "Waiting for Cloudflare Quick Tunnel URL..."
  for _ in $(seq 1 20); do
    URL="$(grep -hEo 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' "$LOG_DIR/tunnel.err.log" "$LOG_DIR/tunnel.log" 2>/dev/null | tail -n 1 || true)"
    if [ -n "$URL" ]; then
      echo "LIVE CLOUDFLARE TUNNEL URL: $URL"
      exit 0
    fi
    sleep 1
  done
  echo "Tunnel started; check $LOG_DIR/tunnel.err.log for your trycloudflare.com URL."
else
  echo "Permanent Named Cloudflare Tunnel is running!"
  echo "Make sure your Cloudflare Zero Trust Public Hostname points to: http://127.0.0.1:8095"
fi
