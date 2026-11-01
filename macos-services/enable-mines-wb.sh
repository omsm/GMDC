#!/bin/bash
# Like: sudo systemctl enable mines-wb.service
# Installs the LaunchAgent so it auto-starts at login / power-on.
# With RunAtLoad, loading also starts it now (similar to enable --now).

set -euo pipefail
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$SCRIPTS/_common.sh"

LABEL="co.gmdc.mines-wb"
OTHER="co.gmdc.mines-checkpoint"

mkdir -p "$AGENTS" "$LOG_DIR"
fix_crlf
chmod_scripts
cleanup_legacy_autostart

# Only one app per Mac
launchctl bootout "gui/$(id -u)/$OTHER" 2>/dev/null || true
rm -f "$AGENTS/${OTHER}.plist"

cp "$SCRIPTS/${LABEL}.plist" "$AGENTS/"

# Load for this session + future logins
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$AGENTS/${LABEL}.plist"

echo "Enabled $LABEL (autostart on login)."
echo "  Plist: $AGENTS/${LABEL}.plist"
launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E '^\s+(state|pid|path)' || true
