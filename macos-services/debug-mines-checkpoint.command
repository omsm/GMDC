#!/bin/bash
# Optional Terminal debug runner (NOT used at boot).

ROOT="/Users/csm-gmdc/GMDC_IOT"
APP_DIR="$ROOT/Mines-Checkpoint"
PY="$APP_DIR/pyenv/bin/python3"

cd "$APP_DIR" || exit 1
echo "=== Mines-Checkpoint DEBUG (Terminal) ==="
echo "Service should be stopped first: bash $ROOT/macos-services/stop-mines-checkpoint.sh"
echo
"$PY" main.py
echo
echo "Exited with code $?"
read -r -p "Press Enter to close..."
