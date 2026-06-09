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

# Main execution
if (-not (Test-Path $DataDir)) {
    Write-Host "Data directory not found: $DataDir" -ForegroundColor Yellow
    return $true
}

if (Test-VaultEncrypted $DataDir) {
    Write-Host ""
    $unlocked = Unlock-DataVault $DataDir $PythonExe $UseHardwareToken
    
    if (-not $unlocked) {
        Write-Host ""
        Write-Host "Cannot proceed without unlocking the vault." -ForegroundColor Red
        $retry = Read-Host "Retry? (y/n)"
        if ($retry -eq 'y') {
            Unlock-DataVault $DataDir $PythonExe $UseHardwareToken
        } else {
            return $false
        }
    }
    
    Write-Host ""
    return $true
} else {
    # Vault not encrypted, proceed normally
    return $true
}
