#!/usr/bin/env bash
# =============================================================================
# Hermes Pendrive_X – Reset Script (macOS / Linux)
# =============================================================================
# Deletes downloaded runtimes and source code to trigger a fresh first‑run
# setup.  Provides soft (keep data) and full (wipe everything) modes.

# Usage:
#   ./reset-unix.sh soft   # Keep data/ (API keys, config, history)
#   ./reset-unix.sh full   # Delete everything including data/
# ============================================================================





set -euo pipefail      # fail on errors, unset vars, or failed pipelines
IFS=$'\n\t'            # safer word splitting

# --------------------[ Constants ]-------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="1.1.0 (IFA​Z – Ethen Hunt)"      # <-- change as needed
LOGFILE="$ROOT/reset.log"
DATE_FMT="%Y-%m-%d %H:%M:%S"

# --------------------[ Helper functions ]------------------------------------
log() {
    local msg=$1
    printf "[%s] %s\n" "$(date +"$DATE_FMT")" "$msg" | tee -a "$LOGFILE"
}

die() {
    log "ERROR: $1"
    exit 1
}

confirm() {
    local prompt=$1 default=$2
    local reply
    read -r -p "$prompt [$default/n] " reply
    [[ -z "$reply" ]] && reply="$default"
    [[ "$reply" == "$default" || "$reply" == "y" || "$reply" == "Y" ]]
}

# --------------------[ Parse arguments ]------------------------------------
MODE="${1:-}"   # empty = interactive

[[ -z "$MODE" ]] && {
    echo "========================================"
    echo "   Hermes Pendrive_X - Reset"
    echo "========================================"
    echo ""
    echo "Select reset mode:"
    echo "  1) soft  – delete runtimes + source, keep data/"
    echo "  2) full  – delete everything, including API keys"
    read -r -p "Enter 1 or 2: " choice
    [[ "$choice" == "2" ]] && MODE=full || MODE=soft
}

case "$MODE" in
    soft|full) ;;   # ok
    *) die "Invalid mode: '$MODE'. Use 'soft' or 'full'." ;;
esac

log "Reset started ($MODE) – version $VERSION"

# --------------------[ Graceful shutdown ]----------------------------------
LOCK_FILE="$ROOT/data/auth.lock"
if [[ -f "$LOCK_FILE" ]]; then
    log "[INFO] Removing auth lock: $LOCK_FILE"
    rm -f "$LOCK_FILE"
fi

# Ask before killing the gateway processes
if confirm "[INFO] Kill any running 'hermes gateway' processes? (y/n) " "y"; then
    # Use pgrep with a precise name if possible; fallback to pkill
    if pgrep -f "hermes.*gateway" >/dev/null 2>&1; then
        log "[INFO] Killing hermes gateway processes ..."
        pkill -f "hermes.*gateway" || true
    else
        log "[INFO] No matching gateway processes found."
    fi
fi

# --------------------[ Build delete list ]---------------------------------
FOLDERS=()
[[ -d "$ROOT/.cache/runtimes" ]]   && FOLDERS+=("$ROOT/.cache/runtimes")
[[ -d "$ROOT/src/hermes-agent" ]] && FOLDERS+=("$ROOT/src/hermes-agent")

if [[ "$MODE" == "full" ]]; then
    [[ -d "$ROOT/data" ]]    && FOLDERS+=("$ROOT/data")
    [[ -d "$ROOT/.cache" ]] && FOLDERS+=("$ROOT/.cache")
fi

[[ ${#FOLDERS[@]} -eq 0 ]] && die "No folders to delete. Exiting."

# --------------------[ Preview && backup (full) ]---------------------------
echo ""
echo "The following folders will be DELETED:"
for f in "${FOLDERS[@]}"; do
    # Show size safely; fallback to 0 on error
    SIZE=$(du -sb "$f" 2>/dev/null | cut -f1 || echo 0)
    HUMAN=$(numfmt --to=iec "$SIZE")
    printf "  - %s (%s)\n" "$f" "$HUMAN"
done

if [[ "$MODE" == "full" && -d "$ROOT/data" ]]; then
    echo ""
    if confirm "Backup 'data/' to 'backup/data-<timestamp>'? (y/n)" "y"; then
        BACKUP_DIR="${ROOT}/backup"
        mkdir -p "$BACKUP_DIR"
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        cp -a "$ROOT/data" "${BACKUP_DIR}/data-${TIMESTAMP}"
        log "[INFO] Backup created at ${BACKUP_DIR}/data-${TIMESTAMP}"
    fi
fi

# Final confirmation
if ! confirm "[WARN] ALL listed folders will be permanently removed. Continue? (y/n)" "y"; then
    log "User cancelled the reset."
    exit 0
fi

# --------------------[ Deletion ]--------------------------------------------
for f in "${FOLDERS[@]}"; do
    if [[ -d "$f" ]]; then
        log "Deleting $f ..."
        rm -rf -- "$f"
        log "Deleted $f"
    fi
done

log "Reset completed successfully."

# --------------------[ Post‑reset instructions ]-----------------------------
echo ""
echo "========================================"
echo "   Reset Complete (${MODE^^})"
echo "========================================"
if [[ "$MODE" == "soft" ]]; then
    echo "Next step: run ./launch.sh to re‑download runtimes."
    echo "Your API keys and config remain in $ROOT/data."
else
    echo "Next step: run ./launch.sh for a completely fresh start."
    echo "You will need to re‑run the setup wizard and re‑enter API keys."
fi

log "Finished script – instructions shown to user."

exit 0