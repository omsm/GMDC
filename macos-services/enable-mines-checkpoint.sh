#!/bin/bash
# Like: sudo systemctl enable mines-checkpoint.service

set -euo pipefail
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPTS/_common.sh"

LABEL="co.gmdc.mines-checkpoint"
OTHER="co.gmdc.mines-wb"

mkdir -p "$AGENTS" "$LOG_DIR"
fix_crlf
chmod_scripts
cleanup_legacy_autostart

launchctl bootout "gui/$(id -u)/$OTHER" 2>/dev/null || true
rm -f "$AGENTS/${OTHER}.plist"

cp "$SCRIPTS/${LABEL}.plist" "$AGENTS/"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENTS/${LABEL}.plist"

echo "Enabled $LABEL (autostart on login)."
echo "  Plist: $AGENTS/${LABEL}.plist"
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E '^\s+(state|pid|path)' || true
