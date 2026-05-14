#!/usr/bin/env bash
# Copy Webots universal_robots sample + conveyor_belt controller into PROJECT_DIR and build.
# macOS default paths. Override: PROJECT_DIR, WEBOTS_HOME

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
WEBOTS_HOME="${WEBOTS_HOME:-/Applications/Webots.app}"

URE_SRC="${WEBOTS_HOME}/Contents/projects/robots/universal_robots"
CONVEYOR_SRC="${WEBOTS_HOME}/Contents/projects/objects/factory/conveyors/controllers/conveyor_belt"
MAKEFILE="${PROJECT_DIR}/controllers/Makefile"

if [[ ! -d "$URE_SRC" ]]; then
  echo "error: missing Webots sample at: $URE_SRC" >&2
  echo "Set WEBOTS_HOME to your Webots.app path if it is installed elsewhere." >&2
  exit 1
fi

if [[ ! -d "$CONVEYOR_SRC" ]]; then
  echo "error: missing conveyor_belt controller at: $CONVEYOR_SRC" >&2
  exit 1
fi

echo "PROJECT_DIR=$PROJECT_DIR"
echo "WEBOTS_HOME=$WEBOTS_HOME"
mkdir -p "$PROJECT_DIR"

echo "Copying universal_robots sample..."
cp -R "${URE_SRC}/." "$PROJECT_DIR/"

echo "Copying conveyor_belt controller..."
mkdir -p "${PROJECT_DIR}/controllers"
cp -R "$CONVEYOR_SRC" "${PROJECT_DIR}/controllers/"

echo "Updating controllers/Makefile (idempotent)..."
if grep -q 'conveyor_belt\.Makefile' "$MAKEFILE" 2>/dev/null; then
  echo "Makefile already lists conveyor_belt; skipping."
else
  sed -i '' 's/^TARGETS = ure_can_grasper\.Makefile$/TARGETS = ure_can_grasper.Makefile conveyor_belt.Makefile/' "$MAKEFILE"
fi

echo "Building controllers..."
export WEBOTS_HOME
cd "${PROJECT_DIR}/controllers"
make clean
if make release; then
  :
else
  echo "make release failed; trying make..."
  make
fi

echo "Done. Open in Webots: ${PROJECT_DIR}/worlds/ure.wbt"
