#!/usr/bin/env bash
# Copy Epson SCARA T6 industrial sample + conveyor_belt controller into a self-contained
# Webots project (controllers resolved from the destination, not Webots.app/projects/...).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default: Webots project root inside this repo (works without write access outside workspace).
# Pass a path to copy elsewhere, e.g. ~/Desktop/scaraT6_webots_standalone
DEFAULT_DEST="${ROOT_DIR}/webots_scara_t6_standalone"
DEST="${1:-$DEFAULT_DEST}"

WEBOTS_SCARA="/Applications/Webots.app/Contents/projects/robots/epson/scara_t6"
WEBOTS_CONVEYOR="/Applications/Webots.app/Contents/projects/objects/factory/conveyors/controllers/conveyor_belt"

if [[ ! -d "$WEBOTS_SCARA" ]]; then
  echo "error: Webots sample not found at: $WEBOTS_SCARA" >&2
  echo "Install Webots R2025a (or adjust WEBOTS_SCARA in this script)." >&2
  exit 1
fi

if [[ ! -d "$WEBOTS_CONVEYOR" ]]; then
  echo "error: conveyor_belt controller not found at: $WEBOTS_CONVEYOR" >&2
  exit 1
fi

mkdir -p "$DEST"

echo "Destination: $DEST"
echo "Copying scara_t6 sample..."
rsync -a --delete "$WEBOTS_SCARA/" "$DEST/"

echo "Copying conveyor_belt controller..."
mkdir -p "$DEST/controllers/conveyor_belt"
rsync -a "$WEBOTS_CONVEYOR/" "$DEST/controllers/conveyor_belt/"

echo "Done. Open in Webots:"
echo "  $DEST/worlds/industrial_example.wbt"
echo ""
echo "In the console, conveyor_belt should start from your project path, not Webots.app."
