#!/bin/bash
#
# Hermes Agent Portable - Vault Unlock Helper (Unix/Linux/macOS)
# This script integrates encryption/decryption into the launch process
#

DATA_DIR="${1:-.\/data}"
PYTHON_EXE="${2:-python3}"

# Check if vault is encrypted
test_vault_encrypted() {
    local data_path="$1"
    local vault_config_path="$data_path/.vault"
    
    if [[ -f "$vault_config_path" ]]; then
        if command -v jq &> /dev/null; then
            encrypted=$(jq -r '.encrypted' "$vault_config_path" 2>/dev/null)
            [[ "$encrypted" == "true" ]]
            return
        else
            # Fallback: check if file contains "encrypted": true
            grep -q '"encrypted"[[:space:]]*:[[:space:]]*true' "$vault_config_path" 2>/dev/null
            return
        fi
    fi
    
    return 1
}

# Unlock the data vault
unlock_data_vault() {
    local data_path="$1"
    local python_path="$2"
    
    echo -e "\033[36m[VAULT] Hermes Agent vault detected.\033[0m"
    echo ""
    
    # Call the security module to decrypt
    "$python_path" -m security decrypt "$data_path"
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        echo -e "\033[32m[OK] Vault unlocked successfully!\033[0m"
        return 0
    else
        echo -e "\033[31m[ERROR] Failed to unlock vault.\033[0m"
        return 1
    fi
}

# Main execution
if [[ ! -d "$DATA_DIR" ]]; then
    echo "Data directory not found: $DATA_DIR" >&2
    exit 0
fi

if test_vault_encrypted "$DATA_DIR"; then
    echo ""

    if ! unlock_data_vault "$DATA_DIR" "$PYTHON_EXE"; then
        echo ""
        echo -e "\033[31mCannot proceed without unlocking the vault.\033[0m"
        read -p "Retry? (y/n) " retry

        if [[ "$retry" == "y" || "$retry" == "Y" ]]; then
            if ! unlock_data_vault "$DATA_DIR" "$PYTHON_EXE"; then
                exit 1
            fi
        else
            exit 1
        fi
    fi

    echo ""
    exit 0
else
    # Vault not encrypted, proceed normally
    exit 0
fi
