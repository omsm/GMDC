#!/bin/bash
# Like: sudo systemctl disable mines-checkpoint.service

set -euo pipefail
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPTS/_common.sh"

LABEL="co.gmdc.mines-checkpoint"
PATTERN="$ROOT/Mines-Checkpoint/pyenv/bin/python3 main.py"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$AGENTS/${LABEL}.plist"
cleanup_legacy_autostart

PIDS=$(pgrep -f "$PATTERN" || true)
if [[ -n "${PIDS}" ]]; then
  kill $PIDS 2>/dev/null || true
  sleep 1
  PIDS2=$(pgrep -f "$PATTERN" || true)
  [[ -n "${PIDS2}" ]] && kill -9 $PIDS2 2>/dev/null || true
fi

echo "Disabled $LABEL (will not autostart at login)."
echo "  Removed: $AGENTS/${LABEL}.plist"
