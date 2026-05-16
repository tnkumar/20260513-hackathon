#!/usr/bin/env bash
# Build controllers, stream service logs in this terminal, open browser, then Webots.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [[ -f "$ROOT/.env" ]]; then
  echo "==> Loading environment from .env"
  while IFS='=' read -r key value; do
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    [[ -z "$key" || "$key" == \#* ]] && continue
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    export "$key=$value"
  done < "$ROOT/.env"
fi

export COORDINATOR_TCP_PORT="${COORDINATOR_TCP_PORT:-9099}"
export FRONTEND_WS_PORT="${FRONTEND_WS_PORT:-8765}"
export AGENT_HTTP_PORT="${AGENT_HTTP_PORT:-8787}"
export ADK_AGENT_PORT="${ADK_AGENT_PORT:-8790}"
export ADK_AGENT_URL="${ADK_AGENT_URL:-http://127.0.0.1:${ADK_AGENT_PORT}/plan}"
export ADK_MODEL="${ADK_MODEL:-gemini-3-flash-preview}"
export USE_ADK="${USE_ADK:-1}"
export SIM_SLOWDOWN="${SIM_SLOWDOWN:-1}"
export UR_SPEED_MULT="${UR_SPEED_MULT:-1}"
export SCARA_SPEED_DIV="${SCARA_SPEED_DIV:-4}"
WEBOTS_HOME="${WEBOTS_HOME:-/Applications/Webots.app}"
WORLD="$ROOT/combined_world/worlds/ure_plus_scara.wbt"

kill_listeners_on_port() {
  local port="$1"
  local pids
  if ! command -v lsof >/dev/null 2>&1; then
    return
  fi
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "==> Stopping stale listener(s) on port $port: $pids"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
  fi
}

echo "==> Clearing stale FactoryFlow services if present"
for port in "$FRONTEND_WS_PORT" "$AGENT_HTTP_PORT" "$ADK_AGENT_PORT" "$COORDINATOR_TCP_PORT" 5173 5174 5175 5176 5177 5178 5179 5180 5181 5182 5183 5184 5185 5186; do
  kill_listeners_on_port "$port"
done
sleep 1

echo "==> Building C controllers (WEBOTS_HOME=$WEBOTS_HOME)"
(cd "$ROOT/combined_world/controllers" && make release WEBOTS_HOME="$WEBOTS_HOME")

echo "==> Installing frontend deps if needed"
cd "$ROOT/frontend"
if [[ ! -d node_modules ]]; then npm install; fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ -x "$ROOT/agent_service/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/agent_service/.venv/bin/python"
fi

PIDS=()

cleanup() {
  echo
  echo "==> Stopping FactoryFlow services"
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    kill "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

start_logged() {
  local name="$1"
  local dir="$2"
  shift 2
  (
    cd "$dir"
    "$@" 2>&1 | sed -u "s/^/[$name] /"
  ) &
  PIDS+=("$!")
}

echo "==> Starting services with logs in this terminal"
start_logged bridge "$ROOT/frontend" node server.mjs
start_logged adk "$ROOT/agent_service" env PYTHONUNBUFFERED=1 "$PYTHON_BIN" server.py
start_logged vite "$ROOT/frontend" npm run dev -- --host 127.0.0.1 --port 5173

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
  "$WEBOTS_CMD" "$WORLD"
  exit $?
fi

echo "==> ERROR: Webots executable not found (tried PATH and \$WEBOTS_HOME/Contents/MacOS/webots)." >&2
echo "    Install Webots or set WEBOTS_HOME to your .app bundle, then re-run this script." >&2
