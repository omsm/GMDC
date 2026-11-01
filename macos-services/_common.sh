#!/bin/bash
# Shared helpers for macos-services install/stop scripts.

ROOT="/Users/csm-gmdc/GMDC_IOT"
SCRIPTS="$ROOT/macos-services"
AGENTS="${HOME}/Library/LaunchAgents"
LOG_DIR="$ROOT/logs"

fix_crlf() {
  local f
  for f in "$SCRIPTS"/*.sh "$SCRIPTS"/*.command "$SCRIPTS"/*.plist; do
    [[ -f "$f" ]] || continue
    sed -i '' $'s/\r$//' "$f" 2>/dev/null || true
  done
}

chmod_scripts() {
  chmod +x "$SCRIPTS"/*.sh "$SCRIPTS"/*.command 2>/dev/null || true
}

# Remove fragile Login Items from earlier Terminal/.command/.app approach.
cleanup_legacy_autostart() {
  local name
  for name in \
    "run-mines-wb-in-terminal" \
    "run-mines-checkpoint-in-terminal" \
    "MinesWBStart" \
    "MinesCheckpointStart" \
    "UNKNOWN"
  do
    osascript -e "tell application \"System Events\" to if exists login item \"$name\" then delete login item \"$name\"" 2>/dev/null || true
  done
}
