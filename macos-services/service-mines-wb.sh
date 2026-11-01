#!/bin/bash
# Durable boot service for Mines-WB (no Terminal, no Login Item).
# launchd KeepAlive supervises this process across macOS updates.

set -euo pipefail

ROOT="/Users/csm-gmdc/GMDC_IOT"
APP_DIR="$ROOT/Mines-WB"
PY="$APP_DIR/pyenv/bin/python3"
SCRIPTS="$ROOT/macos-services"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1

if [[ ! -x "$PY" ]]; then
  echo "ERROR: missing python: $PY" >&2
  exit 78
fi

# Wait for LAN before talking to Modbus / RFID / OCI
bash "$SCRIPTS/wait-for-lan.sh"

cd "$APP_DIR"
# Replace this shell with python so launchd tracks the real app PID
exec "$PY" main.py
