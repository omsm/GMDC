#!/bin/bash
# Durable boot service for Mines-Checkpoint (no Terminal, no Login Item).
# launchd KeepAlive supervises this process across macOS updates.

set -euo pipefail

ROOT="/Users/csm-gmdc/GMDC_IOT"
APP_DIR="$ROOT/Mines-Checkpoint"
PY="$APP_DIR/pyenv/bin/python3"
SCRIPTS="$ROOT/macos-services"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export PYTHONUNBUFFERED=1

if [[ ! -x "$PY" ]]; then
  echo "ERROR: missing python: $PY" >&2
  exit 78
fi

bash "$SCRIPTS/wait-for-lan.sh"

cd "$APP_DIR"
exec "$PY" main.py
