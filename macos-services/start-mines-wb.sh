#!/bin/bash
# Like: sudo systemctl start mines-wb.service
# Starts the service now. Plist must already be enabled (in LaunchAgents).

set -euo pipefail
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPTS/_common.sh"

LABEL="co.gmdc.mines-wb"
PLIST="$AGENTS/${LABEL}.plist"

if [[ ! -f "$PLIST" ]]; then
  echo "Service is not enabled. Run enable first:"
  echo "  bash $SCRIPTS/enable-mines-wb.sh"
  exit 1
fi

fix_crlf
chmod_scripts

if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
else
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
fi

sleep 1
echo "Started $LABEL."
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E '^\s+(state|pid|last exit)' || true
