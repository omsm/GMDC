#!/bin/bash
# Install Python 3.12 on any macOS (Apple Silicon or Intel) via Homebrew,
# and put it ahead of Apple's /usr/bin/python3 (3.9.x) for interactive shells.
#
# Usage (from Terminal):
#   chmod +x python-installer-3-12.sh
#   ./python-installer-3-12.sh
#
# Safe to re-run. Does not remove /usr/bin/python3.
# Skip browser/GUI prompts: NONINTERACTIVE=1 is set for Homebrew when possible.

set -euo pipefail

MARKER_BEGIN="# >>> GMDC Python 3.12 (managed by python-installer-3-12.sh) >>>"
MARKER_END="# <<< GMDC Python 3.12 <<<"

echo "=========================================="
echo " macOS Python 3.12 Setup"
echo "=========================================="
echo ""
echo "This script will:"
echo "  - Install Homebrew if needed"
echo "  - Install python@3.12"
echo "  - Prefer Python 3.12 over Apple's /usr/bin/python3 (3.9.x)"
echo "  - Update your shell startup files (zsh + bash)"
echo ""
echo "Apple's system Python at /usr/bin/python3 is left in place."
echo ""

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "ERROR: This installer is for macOS only." >&2
  exit 1
fi

# --------------------------------------------------
# 1. Architecture + Homebrew prefix
# --------------------------------------------------

echo "[1/7] Detecting Mac architecture..."
ARCH="$(uname -m)"
case "$ARCH" in
  arm64)
    echo "  Apple Silicon (arm64)"
    BREW_PREFIX="/opt/homebrew"
    ;;
  x86_64)
    echo "  Intel (x86_64)"
    BREW_PREFIX="/usr/local"
    ;;
  *)
    echo "ERROR: Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

# --------------------------------------------------
# Helpers
# --------------------------------------------------

ensure_brew_in_path() {
  if [[ -x "${BREW_PREFIX}/bin/brew" ]]; then
    # shellcheck disable=SC1091
    eval "$("${BREW_PREFIX}/bin/brew" shellenv)"
  fi
}

remove_managed_block() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  # Portable: awk works the same under bash (no zsh/sed -i quirks)
  local tmp
  tmp="$(mktemp)"
  awk -v b="$MARKER_BEGIN" -v e="$MARKER_END" '
    $0 == b { skip=1; next }
    $0 == e { skip=0; next }
    !skip { print }
  ' "$file" >"$tmp"
  mv "$tmp" "$file"
}

append_managed_block() {
  local file="$1"
  local py_bin="$2"
  local brew_bin="$3"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  remove_managed_block "$file"
  # PATH only — do NOT alias python/pip (aliases bypass venv and hit
  # Homebrew's externally-managed pip → PEP 668 errors).
  cat >>"$file" <<EOF

${MARKER_BEGIN}
# Prefer Homebrew Python 3.12 over Apple /usr/bin/python3
# When a venv is active, its bin/ is prepended and wins automatically.
export PATH="${py_bin}:${brew_bin}:\$PATH"
# Drop old installer aliases so \`pip3 install\` uses the active venv, not Homebrew.
unalias pip pip3 python python3 2>/dev/null
hash -r 2>/dev/null
${MARKER_END}
EOF
}

# --------------------------------------------------
# 2. Homebrew
# --------------------------------------------------

echo ""
echo "[2/7] Checking Homebrew..."
ensure_brew_in_path

if ! command -v brew >/dev/null 2>&1; then
  echo "  Homebrew not found — installing (may ask for your Mac password)..."
  export NONINTERACTIVE="${NONINTERACTIVE:-1}"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ensure_brew_in_path
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: brew still not on PATH after install." >&2
    echo "Try opening a new Terminal window, then re-run this script." >&2
    exit 1
  fi
else
  echo "  Found: $(brew --version | head -n 1)"
fi

# Persist brew shellenv for Apple Silicon (common miss after first install)
for profile in "$HOME/.zprofile" "$HOME/.bash_profile"; do
  touch "$profile"
  if ! grep -q 'brew shellenv' "$profile" 2>/dev/null; then
    {
      echo ""
      echo "# Homebrew"
      echo "eval \"\$(${BREW_PREFIX}/bin/brew shellenv)\""
    } >>"$profile"
  fi
done

# --------------------------------------------------
# 3. Update Homebrew
# --------------------------------------------------

echo ""
echo "[3/7] Updating Homebrew..."
brew update || echo "  WARN: brew update failed; continuing with current formulae."

# --------------------------------------------------
# 4. Install python@3.12
# --------------------------------------------------

echo ""
echo "[4/7] Installing Python 3.12..."
if brew list --versions python@3.12 >/dev/null 2>&1; then
  echo "  python@3.12 already installed — upgrading if available..."
  brew upgrade python@3.12 >/dev/null 2>&1 || true
else
  brew install python@3.12
fi

# --------------------------------------------------
# 5. Locate binaries (do not rely on brew link; python@3.12 is keg-only)
# --------------------------------------------------

echo ""
echo "[5/7] Locating Python 3.12..."
PYTHON_PREFIX="$(brew --prefix python@3.12)"
# Homebrew puts unversioned python3 / pip3 here:
PYTHON_LIBEXEC="${PYTHON_PREFIX}/libexec/bin"
PYTHON312="${PYTHON_PREFIX}/bin/python3.12"

if [[ ! -x "$PYTHON312" ]]; then
  echo "ERROR: python3.12 not found at $PYTHON312" >&2
  exit 1
fi
if [[ ! -x "${PYTHON_LIBEXEC}/python3" ]]; then
  echo "ERROR: libexec python3 not found at ${PYTHON_LIBEXEC}/python3" >&2
  exit 1
fi

echo "  Prefix : $PYTHON_PREFIX"
echo "  Binary : $PYTHON312"
echo "  ($("$PYTHON312" --version))"

# Current session PATH (no zshrc source — this script is bash)
export PATH="${PYTHON_LIBEXEC}:${BREW_PREFIX}/bin:${PATH:-}"

# Clear stale python/pip aliases from older installer runs so venv pip3 works
# (aliases pointed at Homebrew pip → PEP 668 externally-managed-environment).
unalias pip pip3 python python3 2>/dev/null || true
hash -r 2>/dev/null || true
echo "  Cleared python/pip aliases for this session (unalias + hash -r)."

# --------------------------------------------------
# 6. Shell startup files (zsh + bash) — no `source ~/.zshrc`, no `rehash`
# --------------------------------------------------

echo ""
echo "[6/7] Configuring shell startup files..."

BREW_BIN="${BREW_PREFIX}/bin"
for rc in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bashrc" "$HOME/.bash_profile"; do
  append_managed_block "$rc" "$PYTHON_LIBEXEC" "$BREW_BIN"
  echo "  Updated $rc"
done

echo "  (Skipped sourcing ~/.zshrc from bash — that was the old step-6 crash.)"
echo "  Open a new Terminal tab/window for aliases to load automatically."

# --------------------------------------------------
# 7. Verify with absolute path + PATH
# --------------------------------------------------

echo ""
echo "[7/7] Verifying installation..."
echo "------------------------------------------"
echo "python3.12 (absolute):"
"$PYTHON312" --version
echo "  $PYTHON312"
echo ""
echo "python3 on PATH (this session):"
if command -v python3 >/dev/null 2>&1; then
  python3 --version
  command -v python3
  python3 -c "import sys; print(sys.executable)"
else
  echo "  python3 not on PATH yet in this session (use new Terminal)."
fi
echo "------------------------------------------"

VER="$("$PYTHON312" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$VER" != "3.12" ]]; then
  echo "ERROR: Expected 3.12, got $VER from $PYTHON312" >&2
  exit 1
fi

# Soft check: PATH python3 should be 3.12 in this session after PATH export
PATH_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
if [[ "$PATH_VER" != "3.12" ]]; then
  echo "WARN: This Terminal still sees python3=$PATH_VER"
  echo "      Close Terminal and open a new window, then run: python3 --version"
else
  echo "SUCCESS: python3 on PATH is 3.12 in this session."
fi

echo ""
echo "=========================================="
echo " Python 3.12 Setup Completed"
echo "=========================================="
echo ""
echo "For GMDC apps (new Terminal window):"
echo ""
echo "  python3 --version          # should show 3.12.x"
echo "  cd /path/to/new-IoT"
echo "  python3 -m venv .venv"
echo "  source .venv/bin/activate"
echo "  python -m pip install -U pip"
echo "  python -m pip install -e ../gmdc_common   # from Mines-Checkpoint: ../gmdc_common"
echo "  python -m pip install -r requirements.txt"
echo ""
echo "Always prefer:  python -m pip install ...   (uses the active venv)"
echo "This installer runs: unalias pip pip3 python python3; hash -r"
echo "and writes the same into your shell rc so new Terminals stay clean."
echo ""
echo "If python3 is still 3.9.6 in an old Terminal, open a NEW window."
echo "To skip auto browser later: export GMDC_NO_BROWSER=1"
echo ""
