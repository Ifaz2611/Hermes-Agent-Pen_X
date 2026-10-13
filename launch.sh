#!/usr/bin/env bash
# =============================================================================
# Hermes Agent – Pendrive_X Portable Launcher (macOS / Linux)
# =============================================================================
# Terminal:     ./launch.sh
# macOS Finder: rename this file to "launch.command" for double‑click support.
#
# All data stays inside the "data/" folder; the runtime (Python, Node, uv …) lives
# in ".cache/runtimes/<platform>-<arch>".  The script activates a virtual‑env
# that is built on a real POSIX file‑system (so it works on exFAT USB sticks).
#
# New features in this version:
#   • strict Bash mode (‑Eeuo pipefail)
#   • centralised colour handling (tput) with a non‑interactive fallback
#   • unified logging to $CACHE_DIR/logs/launch.log
#   • small CLI (‑h/‑‑help, ‑‑version, ‑‑silent, ‑‑setup)
#   • cleaner argument parsing (case‑insensitive “hermes” stripping)
#   • robust configuration / PID file parsing
#   • exec() replaces the launcher process when starting Hermes directly
# =============================================================================

# ---------------------------------------------------------------------------
# 0. Bail early if we’re not on a supported platform
# ---------------------------------------------------------------------------

set -Eeuo pipefail
IFS=$'\n\t'

# ---------------------------------------------------------------------------
# 1. Helper: pretty colour printing (uses tput, falls back to plain text)
# ---------------------------------------------------------------------------
_init_colors() {
  # Detect whether stdout is a tty that supports colours
  if [[ -t 1 ]] && command -v tput >/dev/null; then
    local ncolors
    ncolors=$(tput colors 2>/dev/null || echo 0)
    if (( ncolors >= 8 )); then
      RESET=$(tput sgr0)
      BOLD=$(tput bold)
      RED=$(tput setaf 1)
      GREEN=$(tput setaf 2)
      YELLOW=$(tput setaf 3)
      BLUE=$(tput setaf 4)
      MAGENTA=$(tput setaf 5)
      CYAN=$(tput setaf 6)
      WHITE=$(tput setaf 7)
      DIM=$(tput dim)
    else
      RESET='' BOLD='' RED='' GREEN='' YELLOW='' BLUE='' MAGENTA='' CYAN='' WHITE='' DIM=''
    fi
  else
    RESET='' BOLD='' RED='' GREEN='' YELLOW='' BLUE='' MAGENTA='' CYAN='' WHITE='' DIM=''
  fi
}
_init_colors

# ---------------------------------------------------------------------------
# 2. Helper: unified logging (also writes to a file)
#    Usage: log info "human readable message"
#    NOTE: LOGFILE is resolved lazily - PORTABLE_ROOT is defined in section 3.
# ---------------------------------------------------------------------------
log() {
  local level=$1
  shift
  local ts msg logfile
  ts=$(date +'%Y-%m-%d %H:%M:%S')
  msg="[$ts] [$level] $*"
  logfile="${LOGFILE:-${PORTABLE_ROOT:-.}/.cache/logs/launch.log}"
  mkdir -p "$(dirname "$logfile")" 2>/dev/null || true
  printf '%s\n' "$msg" >>"$logfile" 2>/dev/null || true
  printf '%s\n' "$msg"
}

# ---------------------------------------------------------------------------
# 3. Resolve the portable root (absolute path, no trailing slash)
#    NOTE: platform detection happens first (section 4) because RUNTIME_DIR
#    depends on PLATFORM/ARCH. Derived dirs are set in section 4b.
# ---------------------------------------------------------------------------
readonly PORTABLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
HERMES_HOME_BASE="${PORTABLE_ROOT}/data"
HERMES_HOME="${HERMES_HOME_BASE}"
export PORTABLE_ROOT

# ---------------------------------------------------------------------------
# 4. Detect platform / architecture (must precede RUNTIME_DIR resolution)
# ---------------------------------------------------------------------------
OS_RAW="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH_RAW="$(uname -m | tr '[:upper:]' '[:lower:]')"

case "$OS_RAW" in
  linux)   PLATFORM="linux" ;;
  darwin)  PLATFORM="macos" ;;
  *)       log error "Unsupported OS: $OS_RAW"; exit 1 ;;
esac

case "$ARCH_RAW" in
  x86_64|amd64) ARCH="x64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *)             log error "Unsupported architecture: $ARCH_RAW"; exit 1 ;;
esac

# ---------------------------------------------------------------------------
# 4b. Derived directories (safe now that PLATFORM/ARCH are known)
# ---------------------------------------------------------------------------
readonly CACHE_DIR="${PORTABLE_ROOT}/.cache"
readonly SRC_DIR="${PORTABLE_ROOT}/src"
readonly RUNTIME_DIR="${CACHE_DIR}/runtimes/${PLATFORM}-${ARCH}"
readonly LOG_DIR="${CACHE_DIR}/logs"
readonly LOGFILE="${LOG_DIR}/launch.log"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# 5. Small CLI – help, version, silent, forced‑setup, profile
# ---------------------------------------------------------------------------
print_help() {
  cat <<EOF
Hermes Pendrive_X – Portable Launcher

Usage:
  ./launch.sh [options] [hermes <sub‑command>...]

Options:
  -h, --help           Show this help message and exit
  -V, --version        Print launcher version and Hermes version
  -s, --silent         Run non‑interactive (no colour, no pauses)
  --profile <name>     Specify a custom data profile

EOF
}
print_version() {
  local hermes_ver="unknown"
  if [[ -f "${SRC_DIR}/hermes-agent/hermes_cli/__init__.py" ]]; then
    hermes_ver=$(grep -Po '__version__\s*=\s*"\K[^"]+' "${SRC_DIR}/hermes-agent/hermes_cli/__init__.py" || true)
  fi
  printf "%s\n" "Launcher version: 1.0.0 (2025‑11‑17)"
  printf "%s\n" "Hermes version:   %s" "$hermes_ver"
}
OPTION_SILENT=0
OPTION_PROFILE=""
while (( $# )); do
  case "${1,,}" in
    -h|--help)   print_help; exit 0 ;;
    -v|--version) print_version; exit 0 ;;
    -s|--silent) OPTION_SILENT=1; shift ;;
    --profile)   OPTION_PROFILE="$2"; shift 2 ;;
    --setup)     # force re‑run of the setup script even if ready.flag exists
      rm -f "${RUNTIME_DIR}/ready.flag"
      shift ;;
    hermes)      # top‑level hermes command – strip the leading token later
      HERMES_TOP=1; shift ;;
    *) break ;;   # unknown – treat as sub‑command for hermes
  esac
done

# Update HERMES_HOME if profile is specified
if [[ -n "${OPTION_PROFILE}" ]]; then
    HERMES_HOME="${HERMES_HOME_BASE}/profiles/${OPTION_PROFILE}"
    if [[ "${OPTION_SILENT}" -eq 0 ]]; then
        printf "${MAGENTA}[PROFILE]${RESET} Active Profile: ${BOLD}${MAGENTA}%s${RESET}\n" "${OPTION_PROFILE}"
    fi
fi
export HERMES_HOME

# ---------------------------------------------------------------------------
# 6. First‑run (or forced) setup
# ---------------------------------------------------------------------------
if [[ ! -f "${RUNTIME_DIR}/ready.flag" ]]; then
  log info "First‑run setup required – installing runtimes ..."
  cat <<'BANNER'

======================================================================
   Hermes Portable – First Run Setup
======================================================================
BANNER

  echo "  Platform: ${PLATFORM}-${ARCH}"
  echo "  This will download ~600 MB of runtime files."
  echo "  Please be patient."
  echo
  bash "${PORTABLE_ROOT}/scripts/setup-unix.sh" "${PORTABLE_ROOT}"
  if (( $? != 0 )); then
    log error "Runtime‑setup script failed (exit $?)"
    exit 1
  fi
else
  log info "Runtime already prepared (ready.flag present)."
fi

# ---------------------------------------------------------------------------
# 7. Build / locate the portable virtual‑env
# ---------------------------------------------------------------------------
# The pointer file is written by the setup script; fallback to the historic location.
if [[ -f "${RUNTIME_DIR}/venv.path" ]]; then
  VENV_PATH="$(cat "${RUNTIME_DIR}/venv.path")"
else
  VENV_PATH="${RUNTIME_DIR}/venv"
fi
export VIRTUAL_ENV="${VENV_PATH}"

if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
  log info "Local venv not found – rebuilding in /tmp (fast, cache‑aware)."

  # Pick a mount‑point‑independent temporary name (so parallel runs on the same USB
  # do not clash).  We use a hash of the runtime directory; on a clean drive it
  # will be the same.
  if command -v md5sum >/dev/null 2>&1; then
    DRIVE_ID=$(printf '%s' "${RUNTIME_DIR}" | md5sum | cut -c1-8 | tr -d ' \n')
  elif command -v md5 >/dev/null 2>&1; then
    DRIVE_ID=$(printf '%s' "${RUNTIME_DIR}" | md5 | cut -c1-8 | tr -d ' \n')
  else
    DRIVE_ID=$(printf '%s' "${RUNTIME_DIR}" | cksum | cut -c1-8 | tr -d ' \n')
  fi
  TMP_VENV="/tmp/hermes-portable-venv-${DRIVE_ID}"
  export UV_CACHE_DIR="/tmp/hermes-uv-cache-${DRIVE_ID}"
  mkdir -p "${UV_CACHE_DIR}"

  # Save the new location so the next run re‑uses it.
  echo "${TMP_VENV}" > "${RUNTIME_DIR}/venv.path"

  # Remove any stale copy.
  rm -rf "${TMP_VENV}"

  # Build the venv – uv is fast; fall back to plain python‑venv if necessary.
  UV_EXE="${RUNTIME_DIR}/uv/uv"
  PY_EXE="${RUNTIME_DIR}/python/bin/python3"

  if [[ -x "${UV_EXE}" ]] && "${UV_EXE}" venv "${TMP_VENV}" --python "${PY_EXE}" --seed 2>/dev/null; then
    :   # uv succeeded
  else
    "${PY_EXE}" -m venv "${TMP_VENV}"
  fi

  # Install the Hermes package (editable) **and** the Telegram extra.
  # Point all subsequent steps at the rebuilt venv.
  VENV_PATH="${TMP_VENV}"

  if [[ -x "${UV_EXE}" ]] && "${UV_EXE}" pip install \
        --python "${TMP_VENV}/bin/python" \
        --link-mode=copy \
        -e "${SRC_DIR}/hermes-agent[all]" \
        "python-telegram-bot[webhooks]==22.6" 2>/dev/null; then
    :   # uv pip succeeded
  else
    "${TMP_VENV}/bin/python" -m pip install -e "${SRC_DIR}/hermes-agent[all]" "python-telegram-bot[webhooks]==22.6"
  fi

  log ok "Portable venv rebuilt at ${TMP_VENV}"
  readonly VENV_PATH
else
  log info "Using existing venv at ${VENV_PATH}"
  readonly VENV_PATH
fi

# ---------------------------------------------------------------------------
# 8. Activate the venv (prepend its bin to PATH)
# ---------------------------------------------------------------------------
export PATH="${VENV_PATH}/bin:${RUNTIME_DIR}/python/bin:${RUNTIME_DIR}/node/bin:${RUNTIME_DIR}/uv:${RUNTIME_DIR}/bin:${PATH}"
export PYTHONNOUSERSITE=1
export PYTHONHOME=
export PYTHONPATH=
export UV_NO_CONFIG=1
export UV_PYTHON="${RUNTIME_DIR}/python/bin/python3"
export PLAYWRIGHT_BROWSERS_PATH="${RUNTIME_DIR}/playwright"
# Node‑specific tweaks – keep npm isolated from the host.
export NPM_CONFIG_PREFIX="${RUNTIME_DIR}/node"
export NODE_PATH="${RUNTIME_DIR}/node/lib/node_modules"

# Optional:redirect npm config home to a portable place (instead of host HOME)
if [[ "${OPTION_SILENT}" -eq 0 ]]; then
  export NPM_CONFIG_USERCONFIG="${CACHE_DIR}/npm/npmrc"
fi

# ---------------------------------------------------------------------------
# 9. Unlock encrypted data vault (if encrypted)
# ---------------------------------------------------------------------------
if [[ -f "${PORTABLE_ROOT}/scripts/unlock-vault.sh" ]]; then
  bash "${PORTABLE_ROOT}/scripts/unlock-vault.sh" "${HERMES_HOME}" "python3" "false"
  if (( $? != 0 )); then
    log error "Failed to unlock vault or user cancelled."
    exit 1
  fi
else
  log warn "unlock-vault.sh not found – skipping vault unlock."
fi

# ---------------------------------------------------------------------------
# 10. Verify source code
# ---------------------------------------------------------------------------
if [[ ! -d "${SRC_DIR}/hermes-agent" ]]; then
  log error "Hermes source not found in ${SRC_DIR}/hermes-agent"
  exit 1
fi

# ---------------------------------------------------------------------------
# 11. Argument handling
# ---------------------------------------------------------------------------
# If a hermes sub‑command was supplied directly, forward it **without** opening
# the UI.  Handles cases like:
#   launch.sh hermes setup
#   launch.sh hermes chat --model <name>
# NOTE: the leading "hermes" token was already consumed by the
# option-parsing loop above, so no extra shift is needed here.

if (( $# )); then
  case "${1:-}" in
    mcp)
      shift
      log info "Running Hermes MCP Manager ..."
      python3 "${PORTABLE_ROOT}/tools/mcp/mcp_manager.py" "$@"
      exit $?
      ;;
    profile)
      shift
      log info "Running Hermes Profile Manager ..."
      python3 "${PORTABLE_ROOT}/tools/profiles/profile_manager.py" "$@"
      exit $?
      ;;
    *)
      log info "Running hermes sub‑command: $*"
      exec hermes "$@"
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# 11. Status detection – all info gathered in one place
# ---------------------------------------------------------------------------
detect_status() {
  # ---- basic configuration ---------------------------------------------------
  SETUP_STATUS="Not configured"
  SETUP_ICON="[x]"
  SETUP_COLOR="${RED}"

  if [[ -f "${HERMES_HOME}/.env" ]]; then
    # Very permissive – look for any line that looks like “UPPER=…”.
    if grep -E '^[A-Z][A-Za-z0-9_]*=' "${HERMES_HOME}/.env" >/dev/null; then
      SETUP_STATUS="Configured"
      SETUP_ICON="[OK]"
      SETUP_COLOR="${GREEN}"
    fi
  fi

  # ---- provider / default model (YAML) ---------------------------------------
  PROVIDER_NAME="—"
  MODEL_NAME="—"
  if [[ -f "${HERMES_HOME}/config.yaml" ]]; then
    # Assume a simple two‑space indentation format; fallback to first match.
    PROVIDER_NAME=$(grep -E '^[[:space:]]{2,}provider:' "${HERMES_HOME}/config.yaml" \
                     | head -n1 | awk '{print $2}' | tr -d '''"')
    MODEL_NAME=$(grep -E '^[[:space:]]{2,}default:' "${HERMES_HOME}/config.yaml" \
                  | head -n1 | awk '{print $2}' | tr -d '''"')
    # Guard against empty strings.
    [[ -z "$PROVIDER_NAME" ]] && PROVIDER_NAME="—"
    [[ -z "$MODEL_NAME" ]]    && MODEL_NAME="—"
  fi

  # ---- gateway PID & health -------------------------------------------------
  GATEWAY_STATUS="Stopped"
  GATEWAY_ICON="[-]"
  GATEWAY_COLOR="${DIM}"
  GATEWAY_PID=""

  if [[ -f "${HERMES_HOME}/gateway.pid" ]]; then
    # The PID file is usually tiny JSON: {"pid":1234}
    # Use jq if available, otherwise a simple grep.
    if command -v jq >/dev/null; then
      GATEWAY_PID=$(jq -r '.pid // empty' "${HERMES_HOME}/gateway.pid")
    else
      GATEWAY_PID=$(grep -Eo '"pid":[0-9]+' "${HERMES_HOME}/gateway.pid" \
                     | grep -Eo '[0-9]+')
    fi
    [[ -n "$GATEWAY_PID" ]] && {
      # `ps` works even if we lack permission to signal the process.
      if ps -p "$GATEWAY_PID" -o pid= >/dev/null; then
        GATEWAY_STATUS="Running (PID $GATEWAY_PID)"
        GATEWAY_ICON="[OK]"
        GATEWAY_COLOR="${GREEN}"
      else
        GATEWAY_STATUS="Stopped (stale lock)"
        GATEWAY_ICON="[!]"
        GATEWAY_COLOR="${YELLOW}"
      fi
    }
  fi

  # ---- Hermes version --------------------------------------------------------
  HERMES_VERSION="unknown"
  if [[ -f "${SRC_DIR}/hermes-agent/hermes_cli/__init__.py" ]]; then
    HERMES_VERSION=$(grep -Po '__version__\s*=\s*"\K[^"]+' \
                       "${SRC_DIR}/hermes-agent/hermes_cli/__init__.py" | head -n1)
  fi
  # As a last resort, ask the (already‑installed) CLI.
  if [[ "$HERMES_VERSION" == "unknown" ]] && command -v hermes >/dev/null; then
    HERMES_VERSION=$(hermes --version 2>/dev/null | awk '{print $2}')
  fi
}
detect_status

# ---------------------------------------------------------------------------
# 12. UI helpers – colourised echo via `printf`
# ---------------------------------------------------------------------------
spacer() { printf '\n%s\n\n' "$(printf '=%.0s' {1..70})"; }

# Generic coloured printer (fallback to no colour in silent mode)
cprint() {
  local colour="${1:-RESET}" msg="${2:-$1}"
  if [[ "$#" -eq 1 ]]; then colour="RESET"; msg="$1"; fi
  if (( OPTION_SILENT )); then
    printf '%s\n' "$msg"
  else
    case "$colour" in RESET|BOLD|RED|GREEN|YELLOW|BLUE|MAGENTA|CYAN|WHITE|DIM) ;;
      *) colour="RESET" ;;
    esac
    printf '%b\n' "${!colour}${msg}${RESET}"
  fi
}

# ---------------------------------------------------------------------------
# 13. Menus
# ---------------------------------------------------------------------------
show_main_menu() {
  clear
  spacer
  cprint BOLD "HERMES PORTABLE LAUNCHER v${HERMES_VERSION:-unknown}"
  cprint DIM "AI Agent for Everyone"
  spacer

  cprint CYAN "Setup     ${SETUP_COLOR}${SETUP_ICON}${RESET} ${WHITE}${SETUP_STATUS}"
  [[ "$PROVIDER_NAME" != "—" ]] && cprint CYAN "Provider  ${PROVIDER_NAME}"
  [[ "$MODEL_NAME" != "—" ]] && cprint CYAN "Model     ${MODEL_NAME}"
  cprint CYAN "Gateway   ${GATEWAY_COLOR}${GATEWAY_ICON}${RESET} ${WHITE}${GATEWAY_STATUS}"
  cprint CYAN "Version   v${HERMES_VERSION}"
  spacer

  cprint YELLOW "1) Start Hermes Chat"
  cprint YELLOW "2) Setup / Reconfigure Hermes"
  if [[ "$GATEWAY_STATUS" == Running* ]]; then
    cprint YELLOW "3) Stop Gateway ${RED}[live]${RESET}"
  else
    cprint YELLOW "3) Start Gateway"
  fi
  cprint YELLOW "4) Advanced Options   >>>>"
  cprint YELLOW "5) Exit"
  spacer

  # Read the choice – honour silent mode (no pauses)
  if (( OPTION_SILENT )); then
    read -r -p "Enter option (1‑5): " choice || exit 0
  else
    read -r -p "$(cprint CYAN "Select option (1‑5): ") " choice || exit 0
    echo
  fi

  case "$choice" in
    1) menu_chat ;;
    2) menu_setup ;;
    3) menu_gateway ;;
    4) show_advanced_menu ;;
    5) menu_exit ;;
    *) cprint YELLOW "⚠️  Invalid selection – try again."; sleep 1; show_main_menu ;;
  esac
}

show_advanced_menu() {
  clear
  spacer
  cprint BOLD "${WHITE}ADVANCED OPTIONS${RESET}"
  spacer

  cprint YELLOW "1) Run Doctor (check environment)"
  cprint YELLOW "2) View Logs (last 20 lines of gateway.log)"
  cprint YELLOW "3) Edit Config (open config.yaml)"
  cprint YELLOW "4) Restart Gateway"
  cprint YELLOW "5) Update Hermes (pull latest source)"
  cprint YELLOW "6) Back to Main Menu"
  spacer

  if (( OPTION_SILENT )); then
    read -r -p "Select option (1‑6): " adv_choice || return
  else
    read -r -p "$(cprint CYAN "Select option (1‑6): ") " adv_choice || return
    echo
  fi

  case "$adv_choice" in
    1) adv_doctor ;;
    2) adv_view_logs ;;
    3) adv_edit_config ;;
    4) adv_restart_gateway ;;
    5) adv_update ;;
    6) show_main_menu ;;
    *) cprint YELLOW "⚠️  Invalid selection – try again."; sleep 1; show_advanced_menu ;;
  esac
}

# ---------------------------------------------------------------------------
# 14. Action handlers
# ---------------------------------------------------------------------------
menu_chat() {
  clear
  log info "Launching Hermes chat UI ..."
  hermes   # this replaces the launcher process only if we run `exec hermes`
  show_main_menu
}

menu_setup() {
  clear
  log info "Running Hermes setup wizard ..."
  hermes setup
  detect_status
  show_main_menu
}

menu_gateway() {
  clear
  if [[ "$GATEWAY_STATUS" == Running* ]]; then
    log info "Stopping existing gateway ..."
    hermes gateway stop
    if (( $? == 0 )); then
      cprint GREEN "Gateway stopped."
    else
      cprint RED "Failed to stop gateway. Check logs."
    fi
  else
    log info "Starting gateway (background) ..."
    hermes gateway &
    # Give it a moment to create the PID file.
    sleep 2
    cprint CYAN "Gateway started - check ${HERMES_HOME}/gateway.pid."
  fi
  detect_status
  show_main_menu
}

menu_exit() {
  log info "Exiting launcher – thanks for using Hermes Portable."
  exit 0
}

adv_doctor() {
  clear
  log info "Running Hermes Doctor ..."
  hermes doctor
  cprint CYAN "Press Enter to return ..." && read -r
  show_advanced_menu
}

adv_view_logs() {
  clear
  local log_path="${HERMES_HOME}/logs/gateway.log"
  if [[ -f "$log_path" ]]; then
    cprint CYAN "===== GATEWAY LOG (last 20 lines) ====="
    tail -n 20 "$log_path"
    cprint "===== END OF LOG ====="
  else
    cprint YELLOW "No gateway.log file found."
  fi
  cprint CYAN "Press Enter to return ..." && read -r
  show_advanced_menu
}

adv_edit_config() {
  clear
  log info "Opening config.yaml with the default editor ..."
  # Most POSIX systems have `nano` or `vi`, fallback to `cat` if nothing else.
  if command -v nano >/dev/null; then
    nano "${HERMES_HOME}/config.yaml"
  elif command -v vi >/dev/null; then
    vi "${HERMES_HOME}/config.yaml"
  else
    log warn "No known editor found – displaying file with cat."
    cat "${HERMES_HOME}/config.yaml"
  fi
  show_advanced_menu
}

adv_restart_gateway() {
  clear
  log info "Restarting gateway (stop → start) ..."
  hermes gateway restart
  detect_status
  show_main_menu
}

adv_update() {
  clear
  log info "Updating Hermes source to the latest commit ..."
  # You may want a dry‑run switch here; for now we just call the CLI.
  hermes update
  cprint "Update finished – press Enter to continue."
  read -r
  show_advanced_menu
}

# ---------------------------------------------------------------------------
# 15. Cleanup trap – delete the temporary /tmp venv if it was created
# ---------------------------------------------------------------------------
# NOTE: the tmp venv is intentionally kept across runs (venv.path cache).
# Use scripts/reset-unix.sh for a full wipe instead of deleting on EXIT.
cleanup_tmp_venv() {
  # No-op by design; see note above.
  :
}

# ---------------------------------------------------------------------------
# 16. Entry point
# ---------------------------------------------------------------------------
log info "Launcher started – script PID $$"
show_main_menu   # loop until user quits