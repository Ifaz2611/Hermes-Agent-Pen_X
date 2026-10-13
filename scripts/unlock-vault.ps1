# Hermes Agent Portable - Vault Unlock Helper
# This script integrates encryption/decryption into the launch process

param (
    [Parameter(Mandatory=$false)]
    [string]$DataDir = ".\data",
    
    [Parameter(Mandatory=$false)]
    [string]$PythonExe = "python",
    
    [switch]$UseHardwareToken = $false
)

# Check if vault is encrypted
function Test-VaultEncrypted {
    param([string]$DataPath)
    
    $vaultConfigPath = Join-Path $DataPath ".vault"
    if (Test-Path $vaultConfigPath) {
        try {
            $config = Get-Content $vaultConfigPath -Raw | ConvertFrom-Json
            return $config.encrypted -eq $true
        } catch {
            return $false
        }
    }
    return $false
}

# Unlock the vault
function Unlock-DataVault {
    param(
        [string]$DataPath,
        [string]$PythonPath,
        [bool]$UseHardwareToken
    )
    
    Write-Host "Hermes Agent vault detected." -ForegroundColor Cyan
    Write-Host ""
    
    $hardwareTokenArg = if ($UseHardwareToken) { "--hardware-token" } else { "" }
    
    # Call the security module to decrypt
    & $PythonPath -m security decrypt $DataPath $hardwareTokenArg
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Vault unlocked successfully!" -ForegroundColor Green
        return $true
    } else {
        Write-Host "✗ Failed to unlock vault." -ForegroundColor Red
        return $false
    }
}

# Main execution (uses exit codes so launch.bat errorlevel checks work)
if (-not (Test-Path $DataDir)) {
    Write-Host "Data directory not found: $DataDir" -ForegroundColor Yellow
    exit 0
}

if (Test-VaultEncrypted $DataDir) {
    Write-Host ""
    $unlocked = Unlock-DataVault $DataDir $PythonExe $UseHardwareToken

    if (-not $unlocked) {
        Write-Host ""
        Write-Host "Cannot proceed without unlocking the vault." -ForegroundColor Red
        $retry = Read-Host "Retry? (y/n)"
        if ($retry -eq 'y') {
            $unlocked = Unlock-DataVault $DataDir $PythonExe $UseHardwareToken
        }
        if (-not $unlocked) {
            exit 1
        }
    }

    Write-Host ""
    exit 0
} else {
    # Vault not encrypted, proceed normally
    exit 0
}
