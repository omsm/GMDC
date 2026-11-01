#!/bin/bash
# Like: sudo systemctl stop mines-wb.service
# Stops the running process now, but keeps the plist (still enabled for next login).

set -euo pipefail
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPTS/_common.sh"

LABEL="co.gmdc.mines-wb"
PATTERN="$ROOT/Mines-WB/pyenv/bin/python3 main.py"

# Unload from this session only (plist file stays → still "enabled")
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

PIDS=$(pgrep -f "$PATTERN" || true)
if [[ -n "${PIDS}" ]]; then
  kill $PIDS 2>/dev/null || true
  sleep 1
  PIDS2=$(pgrep -f "$PATTERN" || true)
  [[ -n "${PIDS2}" ]] && kill -9 $PIDS2 2>/dev/null || true
fi

echo "Stopped $LABEL (autostart still enabled if plist exists)."
if [[ -f "$AGENTS/${LABEL}.plist" ]]; then
  echo "  Enabled plist still at: $AGENTS/${LABEL}.plist"
  echo "  It will start again at next login, or run: bash $SCRIPTS/start-mines-wb.sh"
else
  echo "  Note: plist missing — service is not enabled. Use enable-mines-wb.sh to enable."
fi
