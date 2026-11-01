#!/bin/bash
# Fix "Operation not permitted" for LaunchAgents in ~/Downloads.
# Moves GMDC_IOT to ~/GMDC_IOT and re-enables the WB or Checkpoint service.

set -euo pipefail

OLD="/Users/csm-gmdc/Downloads/GMDC_IOT"
NEW="/Users/csm-gmdc/GMDC_IOT"

echo "1) Stopping crash-loop / old agents..."
launchctl bootout "gui/$(id -u)/co.gmdc.mines-wb" 2>/dev/null || true
launchctl bootout "gui/$(id -u)/co.gmdc.mines-checkpoint" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/co.gmdc.mines-wb.plist"
rm -f "$HOME/Library/LaunchAgents/co.gmdc.mines-checkpoint.plist"
pkill -f "Mines-WB/pyenv/bin/python3 main.py" 2>/dev/null || true
pkill -f "Mines-Checkpoint/pyenv/bin/python3 main.py" 2>/dev/null || true

if [[ -d "$NEW" ]]; then
  echo "Target already exists: $NEW"
  echo "Using existing folder (not moving)."
elif [[ -d "$OLD" ]]; then
  echo "2) Moving $OLD -> $NEW ..."
  mv "$OLD" "$NEW"
else
  echo "ERROR: neither $OLD nor $NEW found."
  exit 1
fi

echo "3) Clearing quarantine flags..."
xattr -dr com.apple.quarantine "$NEW" 2>/dev/null || true

cd "$NEW/macos-services"
sed -i '' $'s/\r$//' *.sh *.command *.plist 2>/dev/null || true
chmod +x *.sh *.command

echo
echo "Moved/ready at: $NEW"
echo
echo "Now enable ONE service:"
echo "  cd $NEW/macos-services"
echo "  ./enable-mines-wb.sh"
echo "  # or"
echo "  ./enable-mines-checkpoint.sh"
