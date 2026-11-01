#!/bin/bash
# Like: sudo systemctl disable mines-wb.service
# Unloads the agent and removes the plist so it will NOT start at next login.

set -euo pipefail
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPTS/_common.sh"

LABEL="co.gmdc.mines-wb"
PATTERN="$ROOT/Mines-WB/pyenv/bin/python3 main.py"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$AGENTS/${LABEL}.plist"
cleanup_legacy_autostart

# Ensure process is gone
PIDS=$(pgrep -f "$PATTERN" || true)
if [[ -n "${PIDS}" ]]; then
  kill $PIDS 2>/dev/null || true
  sleep 1
  PIDS2=$(pgrep -f "$PATTERN" || true)
  [[ -n "${PIDS2}" ]] && kill -9 $PIDS2 2>/dev/null || true
fi

echo "Disabled $LABEL (will not autostart at login)."
echo "  Removed: $AGENTS/${LABEL}.plist"
