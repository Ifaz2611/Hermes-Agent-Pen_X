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
    if [ -n "${log_file:-}" ]; then
        printf '[%s] [%s] %s\n' "$ts" "$level" "$msg" >> "$log_file"
    fi
}

# Wrapper for curl+wget with retry & checksum support
compute_sha256() {
    local target=$1
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$target" 2>/dev/null | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$target" 2>/dev/null | awk '{print $1}'
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$target" 2>/dev/null
    elif command -v python >/dev/null 2>&1; then
        python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$target" 2>/dev/null
    else
        echo ""
    fi
}

download() {
    local url=$1 dest=$2 expected_hash=${3:-} name
    name=$(basename "$url")
    if [ -f "$dest" ]; then
        local sz
        sz=$(file_size "$dest") || true
        if [ "$sz" -gt 0 ]; then
            if [ -n "$expected_hash" ]; then
                local cached_hash
                cached_hash=$(compute_sha256 "$dest")
                if [ -n "$cached_hash" ] && [ "$cached_hash" != "$expected_hash" ]; then
                    log WARN "$name cached checksum mismatch (expected $expected_hash, got $cached_hash) – re-downloading."
                    rm -f "$dest"
                else
                    log INFO "$name cached and checksum verified ($sz bytes)."
                    return 0
                fi
            else
                log INFO "$name cached ($sz bytes)."
                return 0
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

    if [ ! -f "$dest" ]; then
        fatal "Download succeeded but file not found at $dest"
    fi
    local final_sz
    final_sz=$(file_size "$dest") || true
    if [ "$final_sz" -eq 0 ]; then
        rm -f "$dest"
        fatal "Downloaded file is empty: $name"
    fi

    if [ -n "$expected_hash" ]; then
        local actual_hash
        actual_hash=$(compute_sha256 "$dest")
        if [ -n "$actual_hash" ] && [ "$actual_hash" != "$expected_hash" ]; then
            rm -f "$dest"
            fatal "Checksum verification failed for $name! Expected: $expected_hash, Got: $actual_hash"
        fi
        log INFO "Checksum verified successfully (SHA-256: $actual_hash) for $name"
    fi

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
            if [ -z "${PORTABLE_ROOT:-}" ]; then
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
for cmd in mkdir rm ln cp chmod stat tar gzip; do
    command -v "$cmd" >/dev/null || fatal "Required command not found: $cmd"
done
# At least one of curl/wget is needed for downloads.
if ! command -v curl >/dev/null && ! command -v wget >/dev/null; then
    fatal "Neither curl nor wget available - cannot download runtimes"
fi
# Portable realpath fallback (macOS has no realpath by default).
if ! command -v realpath >/dev/null; then
    realpath() { python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$1"; }
fi

# ------------------------------------------------------------
# Resolve absolute root and derived paths
# ------------------------------------------------------------
ABS_ROOT=$(realpath "${PORTABLE_ROOT:?Provide <portable-root>}" 2>/dev/null) \
    || fatal "Failed to resolve $PORTABLE_ROOT"
CACHE_DIR="$ABS_ROOT/.cache"
SRC_DIR="$ABS_ROOT/src"
# RUNTIME_DIR is resolved AFTER platform detection below.
BIN_DIR=""
mkdir -p "$CACHE_DIR"
TMP_GLOBAL=$(mktemp -d "${CACHE_DIR}/tmp.XXXXXX")

# log_file is initialised after RUNTIME_DIR is resolved below.
log_file=""

# ------------------------------------------------------------
# Platform detection (unified)
# ------------------------------------------------------------
PLATFORM="${HERMES_PLATFORM:-}"
if [ -z "$PLATFORM" ]; then
    OS_RAW="$(uname -s)"
    case "$OS_RAW" in
        Linux*)   PLATFORM="linux" ;;
        Darwin*)  PLATFORM="macos" ;;
        *)        fatal "[WARN] Unsupported OS: $OS_RAW" ;;
    esac
fi

ARCH_OS="${HERMES_ARCH_OS:-$(uname -m)}"
ARCH="${HERMES_ARCH:-}"
if [ -z "$ARCH" ]; then
    case "$ARCH_OS" in
        x86_64|amd64)   ARCH="x64" ;;
        aarch64|arm64)  ARCH="arm64" ;;
        *)              fatal "Unsupported architecture: $ARCH_OS" ;;
    esac
fi

# Derived runtime paths (platform is now known).
RUNTIME_DIR="$CACHE_DIR/runtimes/${PLATFORM}-${ARCH}"
BIN_DIR="${RUNTIME_DIR}/bin"
mkdir -p "$RUNTIME_DIR" "$BIN_DIR" "$SRC_DIR" "$TMP_GLOBAL"
log_file="${RUNTIME_DIR}/setup.log"
: > "$log_file"

# ------------------------------------------------------------
# First-run progress + cancellation handling (P2 UX)
# ------------------------------------------------------------
# Stages are reported to setup-progress.json so the Electron UI can show
# download/setup progress. On INT/TERM the trap preserves logs, removes a
# partial ready.flag, and writes setup-cancelled.flag so the next launch
# resumes in a recoverable state.
SETUP_PROGRESS="${RUNTIME_DIR}/setup-progress.json"
SETUP_CANCELLED_FLAG="${RUNTIME_DIR}/setup-cancelled.flag"
CURRENT_STAGE="starting"
CURRENT_PERCENT=0
SETUP_DONE=0
# Ordered stage list for progress display.
SETUP_STAGES="python node uv ripgrep hermes-source venv python-deps telegram-deps security-deps playwright done"

write_progress() {
    local stage=$1 percent=$2 message=$3
    CURRENT_STAGE="$stage"
    CURRENT_PERCENT="$percent"
    local stages_json="" first=1
    # Mark stages up to the current one as done based on known order.
    local seen_current=0
    for s in $SETUP_STAGES; do
        local st="pending"
        if [ "$s" = "$stage" ]; then st="active"; seen_current=1
        elif [ "$seen_current" = "0" ]; then st="done"
        fi
        [ "$SETUP_DONE" = "1" ] && st="done"
        if [ $first -eq 1 ]; then first=0; else stages_json="${stages_json},"; fi
        stages_json="${stages_json}{\"name\": \"$s\", \"status\": \"$st\", \"done\": $([ "$st" = "done" ] && echo true || echo false)}"
    done
    # Escape double quotes in message for JSON.
    message=$(printf '%s' "$message" | sed 's/\\/\\\\/g; s/"/\\"/g')
    printf '{"stage": "%s", "percent": %s, "message": "%s", "updated_at": "%s", "stages": [%s]}\n' \
        "$stage" "$percent" "$message" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$stages_json" > "$SETUP_PROGRESS" 2>/dev/null || true
}

on_setup_exit() {
    local rc=$?
    # Preserve the temp dir listing in the log, then clean it (logs stay).
    if [ "$SETUP_DONE" != "1" ] && [ "$DRY_RUN" != "true" ]; then
        log WARN "Setup stopped (exit $rc) at stage '$CURRENT_STAGE' — logs preserved at $log_file."
        # Never leave a half-written ready.flag behind; next launch must re-run setup.
        rm -f "${RUNTIME_DIR}/ready.flag"
        printf '{"cancelled": true, "stage": "%s", "exit_code": %s, "at": "%s"}\n' \
            "$CURRENT_STAGE" "$rc" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" > "$SETUP_CANCELLED_FLAG" 2>/dev/null || true
        write_progress "$CURRENT_STAGE" "$CURRENT_PERCENT" "Cancelled at $CURRENT_STAGE (exit $rc). Logs preserved — re-run setup to resume."
        log INFO "Recoverable state: delete nothing; just re-run setup to resume."
    fi
    rm -rf "$TMP_GLOBAL" 2>/dev/null || true
    # Do not override the original exit code.
    exit $rc
}

on_setup_signal() {
    log WARN "Setup cancellation requested — finishing current file operation, then stopping safely."
    # Exit via the EXIT trap so logs/flags are handled in one place.
    exit 130
}

trap on_setup_signal INT TERM
trap on_setup_exit EXIT

# ------------------------------------------------------------
# Build URLs (you can move these into a separate file)
# ------------------------------------------------------------
# NOTE: In a real repo you would generate these from a small JSON/YAML.
# Here we keep them inline for brevity.
case "$ARCH_OS" in
    x86_64|amd64) PYTHON_ARCH="x86_64" ;;
    aarch64|arm64) PYTHON_ARCH="aarch64" ;;
    *) PYTHON_ARCH="$ARCH_OS" ;;
esac

# Load URLs and checksums from versioned manifest (scripts/manifests/runtimes.json)
MANIFEST_SRC="${ABS_ROOT}/scripts/manifests/runtimes.json"
PLATFORM_KEY="${PLATFORM}-${ARCH}"

get_manifest_val() {
    local component=$1 key=$2 fallback=$3
    if [ -f "$MANIFEST_SRC" ]; then
        local val
        val=$(python3 -c "import json,sys; m=json.load(open('$MANIFEST_SRC')); print(m.get('platforms',{}).get('$PLATFORM_KEY',{}).get('$component',{}).get('$key',''))" 2>/dev/null || true)
        if [ -n "$val" ]; then
            echo "$val"
            return 0
        fi
    fi
    echo "$fallback"
}

if [ "$PLATFORM" = "macos" ]; then
    DEFAULT_PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.11.10+20241016-${PYTHON_ARCH}-apple-darwin-install_only.tar.gz"
    if [ "$ARCH" = "arm64" ]; then
        DEFAULT_PY_HASH="5a69382da99c4620690643517ca1f1f53772331b347e75f536088c42a4cf6620"
        DEFAULT_NODE_HASH="e9404633bc02a5162c5c573b1e2490f5fb44648345d64a958b17e325729a5e42"
        DEFAULT_UV_HASH="e4f83fc42d9735512198c2d86a6fc136e2f5a2b59b3ccc4f104018ed07465499"
        DEFAULT_RG_HASH="24ad76777745fbff131c8fbc466742b011f925bfa4fffa2ded6def23b5b937be"
    else
        DEFAULT_PY_HASH="1e23ffe5bc473e1323ab8f51464da62d77399afb423babf67f8e13c82b69c674"
        DEFAULT_NODE_HASH="6698587713ab565a94a360e091df9f6d91c8fadda6d00f0cf6526e9b40bed250"
        DEFAULT_UV_HASH="e069e79f6e0c430d7beaca3025b398980357b8b5c6faa7191032e20d5ee75970"
        DEFAULT_RG_HASH="fc87e78f7cb3fea12d69072e7ef3b21509754717b746368fd40d88963630e2b3"
    fi
    DEFAULT_NODE_URL="https://nodejs.org/dist/v${DEFAULT_NODE_VERSION}/node-v${DEFAULT_NODE_VERSION}-darwin-${ARCH_OS}.tar.gz"
    DEFAULT_UV_URL="https://github.com/astral-sh/uv/releases/download/0.6.8/uv-${PYTHON_ARCH}-apple-darwin.tar.gz"
    DEFAULT_RG_URL="https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-${PYTHON_ARCH}-apple-darwin.tar.gz"
else
    if [ "$ARCH" = "arm64" ]; then
        DEFAULT_PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.11.10+20241016-aarch64-unknown-linux-gnu-install_only.tar.gz"
        DEFAULT_PY_HASH="803e49259280af0f5466d32829cd9d65a302b0226e424b3f0b261f9daf6aee8f"
        DEFAULT_NODE_HASH="08bfbf538bad0e8cbb0269f0173cca28d705874a67a22f60b57d99dc99e30050"
        DEFAULT_UV_HASH="3ffcaa4f4dba917fa58484a1c3dcb96a958a4baca0204e9c10a4799f81b9ee2f"
        DEFAULT_RG_HASH="c827481c4ff4ea10c9dc7a4022c8de5db34a5737cb74484d62eb94a95841ab2f"
        DEFAULT_RG_URL="https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-aarch64-unknown-linux-gnu.tar.gz"
    else
        DEFAULT_PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.11.10+20241016-x86_64-unknown-linux-gnu-install_only.tar.gz"
        DEFAULT_PY_HASH="8b50a442b04724a24c1eebb65a36a0c0e833d35374dbdf9c9470d8a97b164cd9"
        DEFAULT_NODE_HASH="69b09dba5c8dcb05c4e4273a4340db1005abeafe3927efda2bc5b249e80437ec"
        DEFAULT_UV_HASH="2378ea0122bd56a11ee7ae2ad6116c1f22f4657c03b9efb78ac150236bf7974c"
        DEFAULT_RG_HASH="4cf9f2741e6c465ffdb7c26f38056a59e2a2544b51f7cc128ef28337eeae4d8e"
        DEFAULT_RG_URL="https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz"
    fi
    DEFAULT_NODE_URL="https://nodejs.org/dist/v${DEFAULT_NODE_VERSION}/node-v${DEFAULT_NODE_VERSION}-linux-${ARCH_OS}.tar.xz"
    DEFAULT_UV_URL="https://github.com/astral-sh/uv/releases/download/0.6.8/uv-${ARCH_OS}-unknown-linux-gnu.tar.gz"
fi

PYTHON_URL=$(get_manifest_val "python" "url" "$DEFAULT_PY_URL")
PYTHON_SHA256=$(get_manifest_val "python" "sha256" "$DEFAULT_PY_HASH")
NODE_URL=$(get_manifest_val "node" "url" "$DEFAULT_NODE_URL")
NODE_SHA256=$(get_manifest_val "node" "sha256" "$DEFAULT_NODE_HASH")
UV_URL=$(get_manifest_val "uv" "url" "$DEFAULT_UV_URL")
UV_SHA256=$(get_manifest_val "uv" "sha256" "$DEFAULT_UV_HASH")
RG_URL=$(get_manifest_val "rg" "url" "$DEFAULT_RG_URL")
RG_SHA256=$(get_manifest_val "rg" "sha256" "$DEFAULT_RG_HASH")

# ------------------------------------------------------------
# Ready‑flag & manifest handling
# ------------------------------------------------------------
READY_FLAG="${RUNTIME_DIR}/ready.flag"
MANIFEST="${RUNTIME_DIR}/manifest.json"

# If a ready flag exists but any core binary is missing → treat as stale
if [ -f "$READY_FLAG" ]; then
    for core in "python/bin/python3" "node/bin/node" "uv/uv"; do
        if [ ! -x "${RUNTIME_DIR}/${core}" ]; then
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
    if ! download "$PYTHON_URL" "$archive" "$PYTHON_SHA256"; then
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
    if ! download "$NODE_URL" "$archive" "$NODE_SHA256"; then
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
    if ! download "$UV_URL" "$archive" "$UV_SHA256"; then
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
    if ! download "$RG_URL" "$archive" "$RG_SHA256"; then
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
    if ! download "$HERMES_SRC_URL" "$archive"; then
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
    VENV_PYTHON="${venv_dir}/bin/python"
    export VENV_PYTHON
    if [ -d "$venv_dir" ] && [ -x "$VENV_PYTHON" ]; then
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
    chmod +x "$venv_dir/bin/hermes" 2>/dev/null || true
    VENV_PYTHON="${venv_dir}/bin/python"
    export VENV_PYTHON
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
        "${RUNTIME_DIR}/uv/uv" pip install --python "$VENV_PYTHON" --link-mode=copy "python-telegram-bot[webhooks]==22.6"
    else
        "$VENV_PYTHON" -m pip install "python-telegram-bot[webhooks]==22.6"
    fi
    log INFO "Telegram dependencies installed"
}

install_security_deps() {
    [[ "$DRY_RUN" = true ]] && { log INFO "[DRY‑RUN] Would install security deps"; return; }

    log INFO "Installing security dependencies (cryptography, yubikey-manager) ..."
    if [ -x "${RUNTIME_DIR}/uv/uv" ]; then
        "${RUNTIME_DIR}/uv/uv" pip install --python "$VENV_PYTHON" --link-mode=copy \
            "cryptography>=41.0.0" \
            "yubikey-manager>=5.0.0"
    else
        "$VENV_PYTHON" -m pip install \
            "cryptography>=41.0.0" \
            "yubikey-manager>=5.0.0"
    fi
    log INFO "Security dependencies installed"
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
    "manifest_source": "scripts/manifests/runtimes.json",
    "verified": true,
    "versions": {
        "python": "$(basename "$PYTHON_URL" .tar.gz)",
        "python_sha256": "$PYTHON_SHA256",
        "node": "$(basename "$NODE_URL" .tar.gz)",
        "node_sha256": "$NODE_SHA256",
        "uv": "$(basename "$UV_URL" .tar.gz)",
        "uv_sha256": "$UV_SHA256",
        "ripgrep": "$(basename "$RG_URL" .tar.gz)",
        "ripgrep_sha256": "$RG_SHA256",
        "hermes": "$(basename "$HERMES_SRC_URL" .tar.gz)"
    },
    "checksums": {
        "python": "$PYTHON_SHA256",
        "node": "$NODE_SHA256",
        "uv": "$UV_SHA256",
        "ripgrep": "$RG_SHA256"
    },
    "paths": {
        "runtime_dir": "$(realpath "$RUNTIME_DIR" 2>/dev/null || echo "$RUNTIME_DIR")",
        "binary_dir": "$(realpath "$BIN_DIR" 2>/dev/null || echo "$BIN_DIR")",
        "venv_dir": "$(realpath "${RUNTIME_DIR}/venv" 2>/dev/null || echo "${RUNTIME_DIR}/venv")",
        "src_dir": "$(realpath "$SRC_DIR/hermes-agent" 2>/dev/null || echo "$SRC_DIR/hermes-agent")"
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
# Fresh attempt: clear any stale cancellation marker; it is re-created only on failure.
rm -f "$SETUP_CANCELLED_FLAG" 2>/dev/null || true

# Call each step – order matters (progress percents are approximate).
write_progress "python" 5 "Downloading Python runtime…"
install_python
write_progress "node" 20 "Downloading Node.js…"
install_node
write_progress "uv" 32 "Installing uv…"
install_uv
write_progress "ripgrep" 40 "Installing ripgrep…"
install_ripgrep
write_progress "hermes-source" 50 "Fetching Hermes source…"
install_hermes_source

# Only after everything is present do we create the venv
write_progress "venv" 62 "Creating virtual environment…"
setup_venv

# Dependency installation (core → telegram → security → playwright) can be conditional
write_progress "python-deps" 70 "Installing core Python dependencies…"
install_python_deps
write_progress "telegram-deps" 80 "Installing messaging dependencies…"
install_telegram_deps
write_progress "security-deps" 88 "Installing security dependencies…"
install_security_deps
write_progress "playwright" 94 "Installing Playwright browsers…"
install_playwright

# Write lock / manifest flags (skipped in dry-run mode)
if [[ "$DRY_RUN" = true ]]; then
    log INFO "[DRY-RUN] Skipping ready.flag and manifest generation."
else
    touch "$READY_FLAG"
    generate_manifest
    SETUP_DONE=1
    write_progress "done" 100 "Setup completed."
fi

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