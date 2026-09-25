#!/usr/bin/env bash
# Download Homebrew installer + Mosquitto bottles into packaging/macos/vendor/
# (gitignored). Run on the build Mac (needs brew + network once).
#
# Usage:
#   ./packaging/macos/vendor/download_vendor.sh
#   ./packaging/macos/vendor/download_vendor.sh --arch both
#
# Output:
#   packaging/macos/vendor/homebrew/install.sh
#   packaging/macos/vendor/homebrew/brew.tar.gz   (Homebrew/brew source)
#   packaging/macos/vendor/bottles/<arch>/*.bottle.tar.gz (+ manifests)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR_DIR="${SCRIPT_DIR}"
HOMEBREW_DIR="${VENDOR_DIR}/homebrew"
ARCH_MODE="native"  # native | both | arm64 | x86_64

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH_MODE="${2:-native}"; shift 2 ;;
    -h|--help)
      sed -n '1,20p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

BREW_BIN=""
if command -v brew >/dev/null 2>&1; then
  BREW_BIN="$(command -v brew)"
elif [[ -x /opt/homebrew/bin/brew ]]; then
  BREW_BIN="/opt/homebrew/bin/brew"
elif [[ -x /usr/local/bin/brew ]]; then
  BREW_BIN="/usr/local/bin/brew"
fi

if [[ -z "${BREW_BIN}" ]]; then
  echo "ERROR: brew not found on build Mac. Install Homebrew first." >&2
  exit 1
fi

FORMULAE=(
  ca-certificates
  openssl@3
  cjson
  libevent
  libuv
  libwebsockets
  mosquitto
)

arch_list=()
case "${ARCH_MODE}" in
  native)
    case "$(uname -m)" in
      arm64|aarch64) arch_list+=(arm64) ;;
      x86_64|amd64) arch_list+=(x86_64) ;;
      *) echo "ERROR: unsupported arch $(uname -m)" >&2; exit 1 ;;
    esac
    ;;
  both) arch_list+=(arm64 x86_64) ;;
  arm64|x86_64) arch_list+=("${ARCH_MODE}") ;;
  *) echo "ERROR: --arch must be native|both|arm64|x86_64" >&2; exit 1 ;;
esac

mkdir -p "${HOMEBREW_DIR}"

echo "==> Fetching Homebrew install script"
curl -fsSL -A "GMDC-vendor-fetch" -L \
  "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh" \
  -o "${HOMEBREW_DIR}/install.sh"
chmod +x "${HOMEBREW_DIR}/install.sh"

echo "==> Fetching Homebrew/brew source tarball (offline bootstrap)"
# Pin a stable tag — master.tar.gz is unreliable / can be tiny stubs via some CDNs.
BREW_TAG="${HOMEBREW_BREW_TAG:-4.6.15}"
curl -fsSL -A "GMDC-vendor-fetch" -L \
  "https://github.com/Homebrew/brew/archive/refs/tags/${BREW_TAG}.tar.gz" \
  -o "${HOMEBREW_DIR}/brew.tar.gz"
# Sanity: real brew trees are multi-MB
brew_sz=$(wc -c < "${HOMEBREW_DIR}/brew.tar.gz" | tr -d ' ')
if [[ "${brew_sz}" -lt 1000000 ]]; then
  echo "ERROR: brew.tar.gz too small (${brew_sz} bytes) — download failed" >&2
  exit 1
fi

bottle_tag_for_arch() {
  local arch="$1"
  # Prefer current OS bottle tag; fall back to common Sonoma tags.
  local tip
  tip="$("${BREW_BIN}" --repository homebrew/core >/dev/null 2>&1; \
    "${BREW_BIN}" bottle --help >/dev/null; true)"
  unset tip
  case "${arch}" in
    arm64)
      if "${BREW_BIN}" fetch --dry-run --bottle-tag=arm64_sonoma mosquitto >/dev/null 2>&1; then
        echo "arm64_sonoma"
      else
        # Let brew pick for native; for cross we still try sonoma then sequoia
        echo "arm64_sonoma"
      fi
      ;;
    x86_64)
      echo "sonoma"
      ;;
  esac
}

fetch_arch() {
  local arch="$1"
  local out="${VENDOR_DIR}/bottles/${arch}"
  mkdir -p "${out}"
  local tag
  tag="$(bottle_tag_for_arch "${arch}")"
  echo "==> Fetching Mosquitto bottles for ${arch} (tag=${tag})"

  local cache
  cache="$("${BREW_BIN}" --cache)"
  local downloads="${cache}/downloads"
  mkdir -p "${downloads}"

  # Prefer force-bottle with bottle-tag when possible; else native fetch.
  if [[ "$(uname -m)" == "arm64" && "${arch}" == "arm64" ]] || \
     [[ "$(uname -m)" == "x86_64" && "${arch}" == "x86_64" ]]; then
    "${BREW_BIN}" fetch --force-bottle "${FORMULAE[@]}"
  else
    if ! "${BREW_BIN}" fetch --force-bottle --bottle-tag="${tag}" "${FORMULAE[@]}"; then
      echo "WARN: bottle-tag=${tag} failed for ${arch}; trying without tag" >&2
      "${BREW_BIN}" fetch --force-bottle "${FORMULAE[@]}" || true
    fi
  fi

  # Copy bottle archives + manifests into vendor (stable names without hash prefix)
  local f
  for f in "${downloads}"/*; do
    [[ -f "${f}" ]] || continue
    local base
    base="$(basename "${f}")"
    # Keep only our formulae artifacts
    local keep=0
    local formula
    for formula in "${FORMULAE[@]}"; do
      local key="${formula}"
      # openssl@3 appears as openssl@3 in filenames
      if [[ "${base}" == *"--${key}"* ]] || [[ "${base}" == *"--${key}-"* ]] || \
         [[ "${base}" == *"_${key}"* ]]; then
        keep=1
        break
      fi
      # ca-certificates uses double-dash version form
      if [[ "${formula}" == "ca-certificates" && "${base}" == *"ca-certificates"* ]]; then
        keep=1
        break
      fi
    done
    [[ "${keep}" -eq 1 ]] || continue

    # Strip leading hash-- for friendlier local install matching
    local dest_name="${base#*--}"
    if [[ "${dest_name}" == "${base}" ]]; then
      dest_name="${base}"
    fi
    cp -f "${f}" "${out}/${dest_name}"
    # Also keep hashed name so brew cache restore works if needed
    cp -f "${f}" "${out}/${base}"
  done

  local count
  count="$(find "${out}" -name '*.bottle.tar.gz' | wc -l | tr -d ' ')"
  echo "    ${count} bottle archives in ${out}"
  if [[ "${count}" -lt 1 ]]; then
    echo "ERROR: no bottles copied for ${arch}" >&2
    return 1
  fi
}

for a in "${arch_list[@]}"; do
  fetch_arch "${a}"
done

# Marker for build script / runtime
cat > "${VENDOR_DIR}/VENDOR_INFO.txt" <<EOF
GMDC macOS Mosquitto vendor bundle
generated=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host_arch=$(uname -m)
host_os=$(sw_vers -productVersion 2>/dev/null || echo unknown)
brew=${BREW_BIN}
formulae=${FORMULAE[*]}
arches=${arch_list[*]}
EOF

echo ""
echo "==> Vendor ready: ${VENDOR_DIR}"
du -sh "${HOMEBREW_DIR}" "${VENDOR_DIR}/bottles"/* 2>/dev/null || true
