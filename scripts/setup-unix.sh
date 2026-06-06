#!/usr/bin/env bash -eux -o pipefail
# =============================================================================
# Hermes Pendrive_X – Portable Runtime Setup (macOS / Linux)
# =============================================================================
# This script:
#   1. Detects platform/arch.
#   2. Downloads Python 3.11, Node.js, uv, ripgrep, and Hermes source.
#   3. Extracts everything into the cache directory.
#   4. Creates a Python venv, installs packages (core + Telegram + Playwright).
#   5. Emits a manifest and a ready flag.
#
# Usage:
#   ./setup-unix.sh <portable-root> [options]
#
# Options:
#   --skip-uv          Skip uv (will fall back to pip for deps)
#   --skip-rg          Skip ripgrep
#   --skip-playwright  Skip browser download (useful for offline mode)
#   --dry-run          Show what would be done, but don’t modify the tree
#   -h|--help          Print this help
# =============================================================================

# --------------------------- Configurable constants ---------------------------
declare -r DEFAULT_PYTHON_VERSION="3.11.15+20260510"
declare -r DEFAULT_NODE_VERSION="22.14.0"
declare -r DEFAULT_UV_VERSION="0.7.8"
declare -r DEFAULT_RG_VERSION="14.1.1"

# Base URLs – you can override them via environment variables if you fork.
PYTHON_BASE_URL="https://github.com/astral-sh/python-build-standalone/releases/download"
NODE_BASE_URL="https://nodejs.org/dist/v${DEFAULT_NODE_VERSION}"
UV_BASE_URL="https://github.com/astral-sh/uv/releases/download"
RG_BASE_URL="https://github.com/BurntSushi/ripgrep/releases/download"
HERMES_SRC_URL="https://github.com/NousResearch/hermes-agent/archive/refs/heads/main.tar.gz"
# ------------------------------------------------------------------------------

# ---------------------------- Helper functions -----------------------------
# Print usage
usage() {
    grep '^#' "$0" | cut -c4-
    exit 0
}

# Abort with a red‑colored message
fatal() {
    printf '\e[31m[ERROR] %s\e[0m\n' "$*" >&2
    exit 1
}

# Log with timestamp (also written to a file)
log() {
    local level=$1; shift
    local msg=$*
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    printf '[%s] [%s] %s\n' "$ts" "$level" "$msg"
    printf '[%s] [%s] %s\n' "$ts" "$level" "$msg" >> "$log_file"
}

# Wrapper for curl+wget with retry & checksum support
download() {
    local url=$1 dest=$2 name=$(basename "$url")
    if [ -f "$dest" ]; then
        local sz
        sz=$(file_size "$dest") || true
        if [ "$sz" -gt 0 ]; then
            # Verify checksum if we have one (simplified)
            if [ -n "${CHECKSUMS[$name]:-}" ]; then
                echo "$(sha256sum "$dest")" | grep -q "^$(echo "${CHECKSUMS[$name]}" | cut -d' ' -f1) 2>/dev/null"
                if [ $? -ne 0 ]; then
                    log WARN "$name checksum failed – re‑downloading."
                    rm -f "$dest"
                else
                    log INFO "$name cached ($sz bytes)."
                    return 0
                fi
            fi
        fi
    fi
    log INFO "Downloading $name ..."
    if command -v curl >/dev/null; then
        curl -fL --fail --retry 3 --connect-timeout 30 --max-time 600 "$url" -o "$dest"
    elif command -v wget >/dev/null; then
        wget -O "$dest" "$url" --timeout=30 --tries=3
    else
        fatal "Neither curl nor wget available – cannot download $url"
    fi
    [ $? -eq 0 ] || fatal "Download of $url failed"
    log INFO "Download complete ($name)"
}

# Determine file size (portable across GNU and BSD stat)
file_size() {
    local p=$1
    if stat --version >/dev/null 2>&1; then   # GNU stat
        stat -c%s "$p"
    else                                      # BSD stat (macOS)
        stat -f%z "$p"
    fi
}

# Generic extraction – picks the right `tar` flag
extract_archive() {
    local archive=$1 dest=$2
    local ext="${archive##*.}"
    case "$ext" in
        gz|tar.gz)   local cmd='tar -xzf' ;;
        xz|tar.xz)   local cmd='tar -xf'  ;;
        tgz)         local cmd='tar -xzf' ;;
        tar)         local cmd='tar -xf'  ;;
        *)
            fatal "Unsupported archive type: $archive"
            ;;
    esac
    log INFO "Extracting $(basename "$archive") → $dest"
    $cmd "$archive" -C "$dest" --strip-components=1 || {
        rm -rf "$dest"
        rm -f "$archive"
        fatal "Extraction failed for $archive"
    }
}

# Install a binary into $BIN_DIR (creates symlink)
install_binary() {
    local name=$1 archive=$2 dest_sub=$3
    local tmp_dir
    tmp_dir=$(mktemp -d -p "$RUNTIME_DIR" tmp.XXXXXX)

    download "$url" "$archive"
    mkdir -p "$tmp_dir/$dest_sub"
    extract_archive "$archive" "$tmp_dir/$dest_sub"

    # Create symlinks in $BIN_DIR
    local link_path="$BIN_DIR/$name"
    ln -sf "$tmp_dir/$dest_sub/$link" "$link_path"

    # Cleanup
    rm -rf "$tmp_dir"
    log INFO "Binary $name installed and linked to $link_path"
}

# ------------------------------------------------------------
# Parse optional flags
# ------------------------------------------------------------
SKIP_UV=false
SKIP_RG=false
SKIP_PLAYWRIGHT=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-uv)          SKIP_UV=true;          shift ;;
        --skip-rg)          SKIP_RG=true;          shift ;;
        --skip-playwright)  SKIP_PLAYWRIGHT=true;  shift ;;
        --dry-run)          DRY_RUN=true;          shift ;;
        -h|--help)          usage ;;
        *)                  # first positional argument is the root
            if [ -z "$PORTABLE_ROOT" ]; then
                PORTABLE_ROOT=$1
            else
                fatal "Unexpected argument: $1"
            fi
            shift ;;
    esac
done

# ------------------------------------------------------------
# Sanity‑check required tools
# ------------------------------------------------------------
for cmd in realpath mkdir rm ln cp chmod stat sha256sum curl tar gzip xz; do
    command -v "$cmd" >/dev/null || fatal "Required command not found: $cmd"
done

# ------------------------------------------------------------
# Resolve absolute root and derived paths
# ------------------------------------------------------------
ABS_ROOT=$(realpath "${PORTABLE_ROOT:?Provide <portable-root>}" 2>/dev/null) \
    || fatal "Failed to resolve $PORTABLE_ROOT"
CACHE_DIR="$ABS_ROOT/.cache"
SRC_DIR="$ABS_ROOT/src"
RUNTIME_DIR="$CACHE_DIR/runtimes/${PLATFORM}-${ARCH}"
BIN_DIR="${RUNTIME_DIR}/bin"
TMP_GLOBAL=$(mktemp -d -p "$CACHE_DIR" tmp.XXXXXX)

# Keep a log file alongside the runtime – helps with troubleshooting
log_file="${RUNTIME_DIR}/setup.log"
: > "$log_file"

# ------------------------------------------------------------
# Platform detection (unified)
# ------------------------------------------------------------
OS_RAW="$(uname -s)"
ARCH_OS="$(uname -m)"
case "$OS_RAW" in
    Linux*)   PLATFORM="linux" ;;
    Darwin*)  PLATFORM="macos" ;;
    *)        fatal "[WARN] Unsupported OS: $OS_RAW" ;;
esac

# Normalise arch (same logic you already have)
case "$ARCH_OS" in
    x86_64|amd64)   ARCH="x64" ;;
    aarch64|arm64)  ARCH="arm64" ;;
    *)               fatal "Unsupported architecture: $ARCH_OS" ;;
esac

# ------------------------------------------------------------
# Build URLs (you can move these into a separate file)
# ------------------------------------------------------------
# NOTE: In a real repo you would generate these from a small JSON/YAML.
# Here we keep them inline for brevity.
if [ "$PLATFORM" = "macos" ]; then
    PYTHON_ARCH="aarch64"
else
    PYTHON_ARCH="$ARCH_OS"
fi

PYTHON_URL="${PYTHON_BASE_URL}/20260510/cpython-${DEFAULT_PYTHON_VERSION}-${PYTHON_ARCH}-apple-darwin-install_only.tar.gz"
if [ "$PLATFORM" = "macos" ]; then
    NODE_URL="${NODE_BASE_URL}/node-v${DEFAULT_NODE_VERSION}-darwin-${ARCH_OS}.tar.gz"
    UV_URL="${UV_BASE_URL}/${DEFAULT_UV_VERSION}/uv-${PYTHON_ARCH}-apple-darwin.tar.gz"
    RG_URL="${RG_BASE_URL}/${DEFAULT_RG_VERSION}/ripgrep-${DEFAULT_RG_VERSION}-${PYTHON_ARCH}-apple-darwin.tar.gz"
else
    NODE_URL="${NODE_BASE_URL}/node-v${DEFAULT_NODE_VERSION}-linux-${ARCH_OS}.tar.xz"
    UV_URL="${UV_BASE_URL}/${DEFAULT_UV_VERSION}/uv-${ARCH_OS}-unknown-linux-gnu.tar.gz"
    RG_URL="${RG_BASE_URL}/${DEFAULT_RG_VERSION}/ripgrep-${DEFAULT_RG_VERSION}-${ARCH_OS}-unknown-linux-musl.tar.gz"
fi

# ------------------------------------------------------------
# Ready‑flag & manifest handling
# ------------------------------------------------------------
READY_FLAG="${RUNTIME_DIR}/ready.flag"
MANIFEST "${RUNTIME_DIR}/manifest.json"

# If a ready flag exists but any core binary is missing → treat as stale
if [ -f "$READY_FLAG" ]; then
    for core in python node uv; do
        if [ ! -x "${RUNTIME_DIR}/${core}/bin/${core}" ]; then
            log WARN "$core binary missing – re‑initialising runtime folder."
            rm -f "$READY_FLAG"
            break
        fi
    done
fi

# ------------------------------------------------------------
# Main installation blocks (functions make them idempotent)
# ------------------------------------------------------------
install_python() {
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install Python"; return; }

    local archive="${RUNTIME_DIR}/python.tar.gz"
    if ! $DOWNLOAD "$PYTHON_URL" "$archive"; then
        fatal "Failed to download Python $PYTHON_URL"
    fi

    # Extract only if the bin directory is missing
    if [ ! -d "${RUNTIME_DIR}/python/bin" ]; then
        mkdir -p "${RUNTIME_DIR}/python"
        extract_archive "$archive" "${RUNTIME_DIR}/python"
    else
        log INFO "Python already extracted – skipping."
    fi

    # Symlink into $BIN_DIR for convenience
    ln -sf "${RUNTIME_DIR}/python/bin/python3" "$BIN_DIR/python3" || true
    log INFO "Python 3.11 installed at ${RUNTIME_DIR}/python"
}

install_node() {
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install Node.js"; return; }

    local archive="${RUNTIME_DIR}/node.tar.xz"
    if ! $DOWNLOAD "$NODE_URL" "$archive"; then
        fatal "Failed to download Node $NODE_URL"
    fi

    if [ ! -d "${RUNTIME_DIR}/node/bin" ]; then
        mkdir -p "${RUNTIME_DIR}/node"
        extract_archive "$archive" "${RUNTIME_DIR}/node"
    else
        log INFO "Node.js already extracted – skipping."
    fi

    ln -sf "${RUNTIME_DIR}/node/bin/node" "$BIN_DIR/node" || true
    log INFO "Node.js ${DEFAULT_NODE_VERSION} installed"
}

install_uv() {
    [[ "$SKIP_UV" = true ]] && { log INFO "uv install skipped (requested by user)"; return; }

    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install uv"; return; }

    local archive="${RUNTIME_DIR}/uv.tar.gz"
    if ! $DOWNLOAD "$UV_URL" "$archive"; then
        fatal "Failed to download uv $UV_URL"
    fi

    if [ ! -x "${RUNTIME_DIR}/uv/uv" ]; then
        mkdir -p "${RUNTIME_DIR}/uv"
        extract_archive "$archive" "${RUNTIME_DIR}/uv"
    else
        log INFO "uv already present – skipping."
    fi

    ln -sf "${RUNTIME_DIR}/uv/uv" "$BIN_DIR/uv" || true
    log INFO "uv ${DEFAULT_UV_VERSION} installed"
}

install_ripgrep() {
    [[ "$SKIP_RG" = true ]] && { log INFO "ripgrep install skipped"; return; }
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install ripgrep"; return; }

    local archive="${RUNTIME_DIR}/rg.tar.gz"
    if ! $DOWNLOAD "$RG_URL" "$archive"; then
        log WARN "ripgrep download failed – will continue with 'grep' fallback."
        return 0
    fi

    # rg's archive is a flat directory containing a binary called "rg"
    if [ ! -f "${BIN_DIR}/rg" ]; then
        mkdir -p "${RUNTIME_DIR}/rg"
        extract_archive "$archive" "${RUNTIME_DIR}/rg"
        cp "${RUNTIME_DIR}/rg/rg" "$BIN_DIR/rg"
        chmod +x "$BIN_DIR/rg"
    else
        log INFO "ripgrep already present – skipping."
    fi

    log INFO "ripgrep ${DEFAULT_RG_VERSION} installed"
}

install_hermes_source() {
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would fetch Hermes source"; return; }

    local archive="${RUNTIME_DIR}/source.tar.gz"
    if ! $DOWNLOAD "$HERMES_SRC_URL" "$archive"; then
        fatal "Failed to download Hermes source"
    fi

    if [ ! -d "$SRC_DIR/hermes-agent" ]; then
        mkdir -p "$TMP_GLOBAL/source"
        extract_archive "$archive" "$TMP_GLOBAL/source"
        mv "$TMP_GLOBAL/source" "$SRC_DIR/hermes-agent"
    else
        log INFO "Hermes source already present – skipping."
    fi

    log INFO "Hermes source extracted to $SRC_DIR/hermes-agent"
}

setup_venv() {
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would create Python venv"; return; }

    local py_exe="${RUNTIME_DIR}/python/bin/python3"
    if [ ! -x "$py_exe" ]; then
        fatal "Python executable not found at $py_exe"
    fi

    local venv_dir="${RUNTIME_DIR}/venv"
    if [ -d "$venv_dir" ]; then
        log INFO "Virtual environment already exists – skipping creation."
        return 0
    fi

    log INFO "Creating Python virtual environment ($venv_dir) ..."
    uv_exe="${RUNTIME_DIR}/uv/uv"
    if $SKIP_UV && ! command -v uv >/dev/null; then
        fatal "uv is required for venv creation when --skip-uv is set"
    fi

    if [ -x "$uv_exe" ]; then
        "$uv_exe" venv "$venv_dir" --python "$py_exe" || {
            # fall back to the stdlib venv
            log WARN "uv venv failed – using python -m venv"
            "$py_exe" -m venv "$venv_dir"
        }
    else
        "$py_exe" -m venv "$venv_dir"
    fi

    # Ensure the hermes entry‑point is executable
    chmod +x "$venv_dir/bin/hermes" || true
    VENV_PYTHON="${venv_dir}/bin/python"
    log INFO "Virtual environment ready"
}

install_python_deps() {
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install Python deps"; return; }

    log INFO "Installing core Python dependencies (editable) ..."
    # uv pip is preferred because it handles wheels and link‑mode consistently.
    if [ -x "${RUNTIME_DIR}/uv/uv" ]; then
        "${RUNTIME_DIR}/uv/uv" pip install --python "$VENV_PYTHON" --link-mode=copy -e "${SRC_DIR}/hermes-agent[all]"
    else
        "$VENV_PYTHON" -m pip install -e "${SRC_DIR}/hermes-agent[all]"
    fi
    log INFO "Core dependencies installed"
}

install_telegram_deps() {
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install telegram deps"; return; }

    log INFO "Installing python‑telegram‑bot (messaging) ..."
    if [ -x "${RUNTIME_DIR}/uv/uv" ]; then
        "${RUNTIME_DIR}/uv/uv" pip install "$VENV_PYTHON" --link-mode=copy "python-telegram-bot[webhooks]==22.6"
    else
        "$VENV_PYTHON" -m pip install "python-telegram-bot[webhooks]==22.6"
    fi
    log INFO "Telegram dependencies installed"
}

install_playwright() {
    [[ "$SKIP_PLAYWRIGHT" = true ]] && { log INFO "Playwright browsers skipped"; return; }
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install Playwright browsers"; return; }

    log INFO "Installing Playwright browsers (Chromium) ..."
    export PLAYWRIGHT_BROWSERS_PATH="${RUNTIME_DIR}/playwright"
    if "$VENV_PYTHON" -m playwright install chromium; then
        log INFO "Playwright browsers installed"
    else
        log WARN "Playwright browser install failed – Playwright will still work, but some features may be unavailable."
    fi
}

generate_manifest() {
    cat <<EOF > "$MANIFEST"
{
    "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "versions": {
        "python": "$(basename "$PYTHON_URL" .tar.gz)",
        "node": "$(basename "$NODE_URL" .tar.gz)",
        "uv": "$(basename "$UV_URL" .tar.gz)",
        "ripgrep": "$(basename "$RG_URL" .tar.gz)",
        "hermes": "$(basename "$HERMES_SRC_URL" .tar.gz)"
    },
    "paths": {
        "runtime_dir": "$(realpath "$RUNTIME_DIR")",
        "binary_dir": "$(realpath "$BIN_DIR")",
        "venv_dir": "$(realpath "$VENV_DIR")",
        "src_dir": "$(realpath "$SRC_DIR/hermes-agent")"
    }
}
EOF
    log INFO "Manifest written to $MANIFEST"
}

# ------------------------------------------------------------
# Execution flow
# ------------------------------------------------------------
# Initialise the cache directory if it does not exist yet
mkdir -p "$RUNTIME_DIR" "$BIN_DIR" "$SRC_DIR" "$TMP_GLOBAL"

# Call each step – order matters
install_python
install_node
install_uv
install_ripgrep
install_hermes_source

# Only after everything is present do we create the venv
setup_venv

# Dependency installation (core → telegram → playwright) can be conditional
install_python_deps
install_telegram_deps
install_playwright

# Write lock / manifest flags
touch "$READY_FLAG"
generate_manifest

# Cleanup temporary extraction folders
rm -rf "$TMP_GLOBAL"
log INFO "All temporary directories removed"

# ------------------------------------------------------------
# Final user feedback
# ------------------------------------------------------------
log INFO "Setup completed. The hermes entry point is at $VENV_DIR/bin/hermes."
if [ -n "${HERMES_ENTRY:-}" ]; then
    log INFO "Launching hermes now..."
    exec "$VENV_DIR/bin/hermes"
else
    echo "========   Hermes is ready!   ==========" >&2
    echo "To start the agent, run:" >&2
    echo "   $VENV_DIR/bin/hermes" >&2
fi