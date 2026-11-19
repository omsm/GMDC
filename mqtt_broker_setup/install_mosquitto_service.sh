#!/usr/bin/env bash
# Install Mosquitto and keep it running as an OS service (independent of GMDC apps).
# Listeners: 1883 (MQTT TCP), 9001 (WebSocket) — see mosquitto_setup for conf generation.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export GMDC_APP_DATA="${REPO_ROOT}"
export PYTHONPATH="${SCRIPT_DIR}:${REPO_ROOT}"

echo "GMDC Mosquitto install — repo: ${REPO_ROOT}"

if [[ "$(uname -s)" == "Darwin" ]]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew required on macOS. Install from https://brew.sh then re-run."
    exit 1
  fi
  if ! brew list mosquitto >/dev/null 2>&1; then
    echo "Installing mosquitto via Homebrew..."
    brew install mosquitto
  fi
  echo "Writing GMDC mosquitto.conf (1883 + 9001) if needed..."
  python3 <<'PY'
import os
from mosquitto_setup import setup_mosquitto
status = setup_mosquitto(app_data_path=os.environ["GMDC_APP_DATA"])
if not status.get("success"):
    raise SystemExit(status.get("message") or "setup failed")
print(status.get("message") or "ok")
PY
  echo "Starting mosquitto via brew services..."
  brew services start mosquitto || true
elif [[ "$(uname -s)" == "Linux" ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y mosquitto mosquitto-clients
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y mosquitto
  else
    echo "Install mosquitto using your distribution package manager, then enable systemd."
    exit 1
  fi
  python3 <<'PY'
import os
from mosquitto_setup import setup_mosquitto
status = setup_mosquitto(app_data_path=os.environ["GMDC_APP_DATA"])
if not status.get("success"):
    raise SystemExit(status.get("message") or "setup failed")
PY
  sudo systemctl enable mosquitto
  sudo systemctl restart mosquitto
else
  echo "On Windows run the Mosquitto installer or use checkpoint-config vendor bundle."
  echo "Legacy in-app install: set GMDC_ENSURE_MQTT=1 when starting the runtime."
  exit 1
fi

python3 <<'PY'
from ensure import mqtt_ports_ready
import sys
sys.exit(0 if mqtt_ports_ready() else 1)
PY

echo "Mosquitto is up on ports 1883 and 9001."
