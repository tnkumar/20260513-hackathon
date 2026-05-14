#!/usr/bin/env bash
# Build controllers, start WebSocket TCP bridge + Vite, open browser, then Webots.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export COORDINATOR_TCP_PORT="${COORDINATOR_TCP_PORT:-9099}"
export FRONTEND_WS_PORT="${FRONTEND_WS_PORT:-8765}"
export SIM_SLOWDOWN="${SIM_SLOWDOWN:-1}"
export UR_SPEED_MULT="${UR_SPEED_MULT:-10}"
export SCARA_SPEED_DIV="${SCARA_SPEED_DIV:-10}"
WEBOTS_HOME="${WEBOTS_HOME:-/Applications/Webots.app}"
WORLD="$ROOT/combined_world/worlds/ure_plus_scara.wbt"

echo "==> Building C controllers (WEBOTS_HOME=$WEBOTS_HOME)"
(cd "$ROOT/combined_world/controllers" && make release WEBOTS_HOME="$WEBOTS_HOME")

echo "==> Installing frontend deps if needed"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then npm install; fi

echo "==> Starting WS bridge (port $FRONTEND_WS_PORT -> TCP $COORDINATOR_TCP_PORT)"
node server.mjs &
BRIDGE_PID=$!

echo "==> Starting Vite dev server"
npm run dev -- --host 127.0.0.1 --port 5173 &
VITE_PID=$!

cleanup() {
  kill "$BRIDGE_PID" "$VITE_PID" 2>/dev/null || true
}
# Only INT/TERM: if `exec webots` fails we must NOT run cleanup (would kill Vite and break Safari).
trap cleanup INT TERM

sleep 2
if command -v open >/dev/null 2>&1; then
  open "http://127.0.0.1:5173/"
fi

WEBOTS_CMD=""
if command -v webots >/dev/null 2>&1; then
  WEBOTS_CMD=$(command -v webots)
elif [[ -x "$WEBOTS_HOME/Contents/MacOS/webots" ]]; then
  WEBOTS_CMD="$WEBOTS_HOME/Contents/MacOS/webots"
fi

if [[ -n "$WEBOTS_CMD" ]]; then
  echo "==> Launching Webots: $WEBOTS_CMD"
  exec "$WEBOTS_CMD" "$WORLD"
fi

echo "==> ERROR: Webots executable not found (tried PATH and \$WEBOTS_HOME/Contents/MacOS/webots)." >&2
echo "    Install Webots or set WEBOTS_HOME to your .app bundle, then re-run this script." >&2
echo "==> Leaving bridge + Vite running. Use http://127.0.0.1:5173/ in Safari — Ctrl+C here to stop." >&2
wait "$VITE_PID"
cleanup
