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
# ---------------------------------------------------------------------------
readonly LOGFILE="${PORTABLE_ROOT}/.cache/logs/launch.log"
log() {
  local level=$1
  shift
  local ts msg
  ts=$(date +'%Y-%m-%d %H:%M:%S')
  msg="[$ts] [$level] $*"
  printf '%b\n' "$msg" | tee -a "$LOGFILE"
  # When the script is run non‑interactively we still want the file to stay up‑to‑date
  if [[ "${LOGFILE}" != "" ]]; then printf '%s\n' "$msg" >>"$LOGFILE"; fi
}

# ---------------------------------------------------------------------------
# 3. Resolve the portable root (absolute path, no trailing slash)
# ---------------------------------------------------------------------------
readonly PORTABLE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly HERMES_HOME="${PORTABLE_ROOT}/data"
readonly CACHE_DIR="${PORTABLE_ROOT}/.cache"
readonly SRC_DIR="${PORTABLE_ROOT}/src"
readonly RUNTIME_DIR="${CACHE_DIR}/runtimes/${PLATFORM}-${ARCH}"
readonly LOG_DIR="${CACHE_DIR}/logs"
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# 4. Detect platform / architecture
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
# 5. Small CLI – help, version, silent, forced‑setup
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
while (( $# )); do
  case "${1,,}" in
    -h|--help)   print_help; exit 0 ;;
    -v|--version) print_version; exit 0 ;;
    -s|--silent) OPTION_SILENT=1; shift ;;
    --setup)     # force re‑run of the setup script even if ready.flag exists
      rm -f "${RUNTIME_DIR}/ready.flag"
      shift ;;
    hermes)      # top‑level hermes command – strip the leading token later
      HERMES_TOP=1; shift ;;
    *) break ;;   # unknown – treat as sub‑command for hermes
  esac
done

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

readonly VENV_PATH
export VIRTUAL_ENV="${VENV_PATH}"

if [[ ! -x "${VENV_PATH}/bin/python" ]]; then
  log info "Local venv not found – rebuilding in /tmp (fast, cache‑aware)."

  # Pick a mount‑point‑independent temporary name (so parallel runs on the same USB
  # do not clash).  We use a hash of the runtime directory; on a clean drive it
  # will be the same.
  DRIVE_ID=$(echo "${RUNTIME_DIR}" | md5sum | cut -c1-8 | tr -d ' \n')
  TMP_VENV="/tmp/hermes‑portable‑venv‑${DRIVE_ID}"
  export UV_CACHE_DIR="/tmp/hermes‑uv‑cache-${DRIVE_ID}"
  mkdir -p "${UV_CACHE_DIR}"

  # Save the new location so the next run re‑uses it.
  echo "${TMP_VENV}" > "${RUNTIME_DIR}/venv.path"

  # Remove any stale copy.
  rm -rf "${TMP_VENV}"

  # Build the venv – uv is fast; fall back to plain python‑venv if necessary.
  UV_EXE="${RUNTIME_DIR}/uv/uv"
  PY_EXE="${RUNTIME_DIR}/python/bin/python3"

  if "${UV_EXE}" venv "${TMP_VENV}" --python "${PY_EXE}" --seed 2>/dev/null; then
    :   # uv succeeded
  else
    "${PY_EXE}" -m venv "${TMP_VENV}"
  fi

  # Install the Hermes package (editable) **and** the Telegram extra.
  PIP_CMD="${VENV_PATH}/bin/python -m pip"
  if "${UV_EXE}" pip install \
        --python "${TMP_VENNV}/bin/python" \
        --link-mode=copy \
        -e "${SRC_DIR}/hermes-agent[all]" \
        "python-telegram-bot[webhooks]==22.6" 2>/dev/null; then
    :   # uv pip succeeded
  else
    "${PIP_CMD}" install -e "${SRC_DIR}/hermes-agent[all]" "python-telegram-bot[webhooks]==22.6"
  fi

  log ok "Portable venv rebuilt at ${TMP_VENV}"
else
  log info "Using existing venv at ${VENV_PATH}"
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
# 9. Verify source code
# ---------------------------------------------------------------------------
if [[ ! -d "${SRC_DIR}/hermes-agent" ]]; then
  log error "Hermes source not found in ${SRC_DIR}/hermes-agent"
  exit 1
fi

# ---------------------------------------------------------------------------
# 10. Argument handling
# ---------------------------------------------------------------------------
# If a hermes sub‑command was supplied directly, forward it **without** opening
# the UI.  Handles cases like:
#   launch.sh hermes setup
#   launch.sh hermes chat --model <name>
if [[ "${HERMES_TOP:-0}" -eq 1 ]]; then
  shift   # remove the stripped “hermes” token
fi

if (( $# )); then
  log info "Running hermes sub‑command: $*"
  exec hermes "$@"
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
  GATEWAY_COLOR="${GRAY}"
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
  local colour=$1 msg=$2
  if (( OPTION_SILENT )); then
    printf '%s\n' "$msg"
  else
    colour=${colour:-RESET}
    printf '%b\n' "${!colour}${msg}${RESET}"
  fi
}

# ---------------------------------------------------------------------------
# 13. Menus
# ---------------------------------------------------------------------------
show_main_menu() {
  clear
  spacer
  cprint BOLD "${BRIGHT_WHITE}HERMES PORTABLE LAUNCHER v$(detect_status | grep -o 'v[^ ]*')"
  cprint DIM "AI Agent for Everyone"
  spacer

  cprint CYAN "Setup     ${SETUP_COLOR}${SETUP_ICON}${RESET} ${WHITE}${SETUP_STATUS}"
  [[ "$PROVIDER_NAME" != "—" ]] && cprint CYAN "Provider  ${PROVIDER_NAME}"
  [[ "$MODEL_NAME" != "—" ]] && cprint CYAN "Model     ${MODEL_NAME}"
  cprint CYAN "Gateway   ${GATEWAY_COLOR}${GATEWAY_ICON}${RESET} ${WHITE}${GATEWAY_STATUS}"
  cprint CYAN "Version   ${GRAY}v${HERMES_VERSION}"
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
    read -r -p "$(cprint BRIGHT_CYAN "Select option (1‑5): ") " choice || exit 0
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
  cprint BOLD "${BRIGHT_WHITE}ADVANCED OPTIONS${RESET}"
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
    read -r -p "$(cprint BRIGHT_CYAN "Select option (1‑6): ") " adv_choice || return
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
    cprint CYAN "Gateway started – you may see a new entry in the PID table.")
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
  cprint "Press Enter to return …" && read -r
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
  cprint "Press Enter to return …" && read -r
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
cleanup_tmp_venv() {
  if [[ -f "${RUNTIME_DIR}/venv.path" ]]; then
    local tmp_path
    tmp_path=$(cat "${RUNTIME_DIR}/venv.path")
    if [[ "$tmp_path" != "${RUNTIME_DIR}/venv" && -d "$tmp_path" ]]; then
      log info "Removing temporary venv ${tmp_path}"
      rm -rf "$tmp_path"
    fi
  fi
}
trap cleanup_tmp_venv EXIT

# ---------------------------------------------------------------------------
# 16. Entry point
# ---------------------------------------------------------------------------
log info "Launcher started – script PID $$"
show_main_menu   # loop until user quits