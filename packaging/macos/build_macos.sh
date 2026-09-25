#!/usr/bin/env bash
# Build offline Mines-Automation bundle for macOS (PyInstaller onefile).
#
# Usage (from any cwd, on an Apple Silicon or Intel Mac with network once):
#   ./packaging/macos/build_macos.sh
#
# Output:
#   dist/Mines-Automation/
#     iot-configuration
#     automation
#     mines-checkpoint
#     mines-weighbridge
#     iot_configuration.json   (template / last known)
#     conversion.py
#     timeout_config.py
#     .env
#     voice/
#
# Target Macs: copy the whole Mines-Automation folder. No Python install needed.
# Prerequisite on target: Mosquitto MQTT broker already installed & able to listen
# on 1883 / 9001 (Homebrew mosquitto or pkg). Broker install needs internet once
# per machine OR ship Mosquitto separately — the Python apps themselves are offline.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV="${SCRIPT_DIR}/.venv"
BUILD_DIR="${SCRIPT_DIR}/build"
DIST_DIR="${SCRIPT_DIR}/dist"
BUNDLE="${REPO_ROOT}/dist/Mines-Automation"

PY_BIN="${PYTHON:-python3}"

echo "==> Repo:   ${REPO_ROOT}"
echo "==> Bundle: ${BUNDLE}"

if ! command -v "${PY_BIN}" >/dev/null 2>&1; then
  echo "ERROR: ${PY_BIN} not found. Install Python 3.11+ on the build Mac only." >&2
  exit 1
fi

echo "==> Creating venv at ${VENV}"
"${PY_BIN}" -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

python -m pip install --upgrade pip wheel setuptools

echo "==> Installing application dependencies (build Mac only)"
pip install -r "${REPO_ROOT}/checkpoint-config/requirements.txt"
pip install -r "${REPO_ROOT}/Mines-Checkpoint/requirements.txt"
pip install -r "${REPO_ROOT}/Mines-WB/requirements.txt"
pip install -e "${REPO_ROOT}/gmdc_common"
# pywebview cocoa backend on macOS
pip install 'pyobjc-core>=10' 'pyobjc-framework-Cocoa>=10' 'pyobjc-framework-WebKit>=10' || true
pip install 'PyInstaller==6.11.1'

mkdir -p "${BUILD_DIR}" "${DIST_DIR}" "${BUNDLE}"

build_one() {
  local spec="$1"
  echo ""
  echo "==> PyInstaller: $(basename "${spec}")"
  pyinstaller \
    --noconfirm \
    --clean \
    --distpath "${DIST_DIR}" \
    --workpath "${BUILD_DIR}" \
    "${spec}"
}

build_one "${SCRIPT_DIR}/iot_configuration.spec"
build_one "${SCRIPT_DIR}/automation.spec"
build_one "${SCRIPT_DIR}/mines_checkpoint.spec"
build_one "${SCRIPT_DIR}/mines_weighbridge.spec"

echo "==> Assembling Mines-Automation/"
rm -rf "${BUNDLE}"
mkdir -p "${BUNDLE}/voice"

cp -f "${DIST_DIR}/iot-configuration" "${BUNDLE}/iot-configuration"
cp -f "${DIST_DIR}/automation" "${BUNDLE}/automation"
cp -f "${DIST_DIR}/mines-checkpoint" "${BUNDLE}/mines-checkpoint"
cp -f "${DIST_DIR}/mines-weighbridge" "${BUNDLE}/mines-weighbridge"
chmod +x \
  "${BUNDLE}/iot-configuration" \
  "${BUNDLE}/automation" \
  "${BUNDLE}/mines-checkpoint" \
  "${BUNDLE}/mines-weighbridge"

# Editable sidecars (NOT baked into the binaries)
cp -f "${REPO_ROOT}/checkpoint-config/conversion.py" "${BUNDLE}/conversion.py"
cp -f "${REPO_ROOT}/checkpoint-config/timeout_config.py" "${BUNDLE}/timeout_config.py"

if [[ -f "${REPO_ROOT}/checkpoint-config/iot_configuration.json" ]]; then
  cp -f "${REPO_ROOT}/checkpoint-config/iot_configuration.json" "${BUNDLE}/iot_configuration.json"
elif [[ -f "${REPO_ROOT}/Mines-Checkpoint/iot_configuration.json" ]]; then
  cp -f "${REPO_ROOT}/Mines-Checkpoint/iot_configuration.json" "${BUNDLE}/iot_configuration.json"
else
  echo '{"checkpoint_type":"mines_entry"}' > "${BUNDLE}/iot_configuration.json"
fi

# Prefer Mines-WB .env (has voice/digitizer knobs); fall back to Checkpoint
if [[ -f "${REPO_ROOT}/Mines-WB/.env" ]]; then
  cp -f "${REPO_ROOT}/Mines-WB/.env" "${BUNDLE}/.env"
elif [[ -f "${REPO_ROOT}/Mines-Checkpoint/.env" ]]; then
  cp -f "${REPO_ROOT}/Mines-Checkpoint/.env" "${BUNDLE}/.env"
else
  touch "${BUNDLE}/.env"
fi

if [[ -d "${REPO_ROOT}/Mines-WB/voice" ]]; then
  rsync -a --delete "${REPO_ROOT}/Mines-WB/voice/" "${BUNDLE}/voice/"
fi

# Clear quarantine so Gatekeeper does not block copy-pasted binaries on other Macs
# (still unsigned — first open may need right-click → Open, or xattr strip again).
if command -v xattr >/dev/null 2>&1; then
  xattr -cr "${BUNDLE}" || true
fi

cat > "${BUNDLE}/README-DEPLOY.txt" <<'EOF'
Mines-Automation (macOS offline bundle)
=======================================

Layout:
  iot-configuration     run FIRST on a new site — pick automation type & hardware
  automation            reads iot_configuration.json and starts the right runtime
  mines-checkpoint      checkpoint family (mines_entry, tracking_*, mines_exit)
  mines-weighbridge     weighbridge family (tare_wb, vadaghat_wb, gross_wb)
  iot_configuration.json
  conversion.py         editable digitizer parse helpers (config UI)
  timeout_config.py     editable timeouts
  .env                  optional env overrides
  voice/                weighbridge announcements

First run on site:
  1. Ensure Mosquitto is installed and can bind 1883 + 9001 (one-time OS setup).
  2. Open Terminal in this folder:
       ./iot-configuration
  3. Complete commissioning (checkpoint_type saved into iot_configuration.json).
  4. Start runtime:
       ./automation

Copy/paste this whole folder to other Macs. No Python install required.
If macOS blocks the app: right-click → Open, or:
  xattr -cr .
EOF

echo ""
echo "==> Done."
echo "    Bundle: ${BUNDLE}"
du -sh "${BUNDLE}"/* 2>/dev/null | sort -h || ls -lah "${BUNDLE}"
echo ""
echo "Copy ${BUNDLE} to the target Mac. Run ./iot-configuration then ./automation."
