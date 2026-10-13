<# 
.SYNOPSIS
    Hermes Pendrive_X – Reset Script (Windows)

.DESCRIPTION
    Deletes downloaded runtimes and source code to force a fresh first‑run.
    Supports two modes:
        • soft  – removes runtimes + source, keeps the data folder (API keys, config,
                  chat history).
        • full  – removes everything, including the data folder.

    The script is safe, logs its actions and can be run non‑interactively
    with the -Force switch.

.NOTES
    v1.2.0 – Ethen Hunt (IFA​Z) – adapted from the Unix reset script.
    Tested on PowerShell 7 (pwsh) and Windows PowerShell 5.1.

.EXAMPLE
    .\scripts\reset-windows.ps1 -Mode soft      # Interactive but keeps data
    .\scripts\reset-windows.ps1 -Mode full -Force   # Fully automated full reset
#>




param(
    [ValidateSet('soft','full')]
    [string] $Mode = '',

    # Skip the “yes/no” prompt – useful for CI or automated provisioning
    [switch] $Force
)

# -------------------------------------------------------------------------
# General PowerShell hardening
# -------------------------------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'          # Fail fast on any error

# -------------------------------------------------------------------------
# Constants & helpers
# -------------------------------------------------------------------------
$Root   = Split-Path -Path $PSScriptRoot -Parent
$LogFile = Join-Path $Root 'reset.log'
$Timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

function Write-Log {
    param([string]$Message, [ConsoleColor]$Color = $Host.UI.RawUI.ForegroundColor)
    $line = "[$Timestamp] $Message"
    Write-Host $line -ForegroundColor $Color
    $line | Out-File -FilePath $LogFile -Encoding utf8 -Append
}

function Ask-Confirmation {
    param([string]$Prompt, [string]$Default = 'yes')
    if ($Force) { return $true }   # No prompt when -Force is supplied

    $answer = Read-Host "$Prompt [$Default/n]"
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = $Default }
    return $answer -match '^(y|yes)$'
}

# -------------------------------------------------------------------------
# Resolve mode (interactive fallback)
# -------------------------------------------------------------------------
if (-not $Mode) {
    Write-Log 'No mode supplied – entering interactive selection' Yellow

    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host '   Hermes Pendrive_X - Reset'           -ForegroundColor Cyan
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host ''
    Write-Host 'Choose reset mode:'                     -ForegroundColor Yellow
    Write-Host '  [1] Soft reset  - Delete runtimes + source, keep data' -ForegroundColor Yellow
    Write-Host '  [2] Full reset  - Delete everything including data'   -ForegroundColor Yellow
    Write-Host ''
    $choice = Read-Host 'Enter 1 or 2'
    switch ($choice) {
        '2' { $Mode = 'full' }
        default { $Mode = 'soft' }
    }
}
Write-Log "Reset mode selected: $Mode" Cyan

# -------------------------------------------------------------------------
# 1️⃣ Stop any running Hermes gateway
# -------------------------------------------------------------------------
$LockFile = Join-Path $Root 'data\auth.lock'
if (Test-Path $LockFile) {
    Write-Log "[INFO] Removing auth lock: $LockFile" Yellow
    Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
}

# Find processes whose command line contains "hermes*gateway*"
$processes = Get-CimInstance -ClassName Win32_Process |
    Where-Object { $_.CommandLine -like '*hermes*gateway*' }

if ($processes) {
    Write-Log "[INFO] Detected $($processes.Count) Hermes gateway process(es)" Yellow
    if (Ask-Confirmation 'Kill the gateway processes now? (y/n)' 'y') {
        foreach ($proc in $processes) {
            try {
                Write-Log "[KILL] PID $($proc.ProcessId) – $($proc.Name)" Yellow
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            } catch {
                Write-Log "  ❗ Failed to stop PID $($proc.ProcessId): $_" Red
            }
        }
    }
} else {
    Write-Log '[INFO] No Hermes gateway processes were found running.' Green
}

# -------------------------------------------------------------------------
# 2️⃣ Build the list of folders to delete
# -------------------------------------------------------------------------
$foldersToDelete = @()

# Helpers for path building (avoids escaping headaches)
# NOTE: scriptblocks get their own scope, so the list lives in script: scope.
$script:foldersToDelete = @()
$AddFolder = {
    param($PathPart)
    $full = Join-Path $Root $PathPart
    if (Test-Path $full) { $script:foldersToDelete += $full }
}

# Runtime & source – always present in the list
& $AddFolder '.cache\runtimes'
& $AddFolder 'src\hermes-agent'

if ($Mode -eq 'full') {
    & $AddFolder 'data'          # Whole data directory
    & $AddFolder '.cache'        # Cache root (contains runtimes etc.)
}

# Remove accidental duplicates – harmless but tidy
$script:foldersToDelete = @($script:foldersToDelete | Sort-Object -Unique)
$foldersToDelete = $script:foldersToDelete
if (-not $foldersToDelete) {
    Write-Log "❌ No folders to delete – aborting." Red
    exit 1
}

# -------------------------------------------------------------------------
# 3️⃣ Show preview (size, colour‑coded) – optional for huge trees
# -------------------------------------------------------------------------
Write-Host ''
Write-Host 'The following folders will be DELETED:' -ForegroundColor Yellow

foreach ($folder in $foldersToDelete) {
    # ---- size (recursive approximation; DirectoryInfo has no .Length) ----
    try {
        $sizeBytes = (Get-ChildItem -LiteralPath $folder -Recurse -File -ErrorAction Stop |
            Measure-Object -Property Length -Sum).Sum
        if (-not $sizeBytes) { $sizeBytes = 0 }
        $sizeMB = [math]::Round($sizeBytes / 1MB, 1)
    } catch {
        $sizeMB = '??'                               # could be locked or hidden
    }

    Write-Host "  - $folder ($sizeMB MB)" -ForegroundColor Red
}

if ($Mode -eq 'soft') {
    Write-Host ''
    Write-Host 'Your data folder is PRESERVED:' -ForegroundColor Green
    Write-Host "  - $Root\data\.env        (API keys)"
    Write-Host "  - $Root\data\config.yaml  (settings)"
    Write-Host "  - $Root\data\sessions\    (chat history)"
}

# -------------------------------------------------------------------------
# 4️⃣ Final confirmation (or skip with -Force)
# -------------------------------------------------------------------------
if (Ask-Confirmation 'Proceed with deletion? (y/n)' 'yes') {
    # Continue
} else {
    Write-Log 'User cancelled the operation – no changes made.' Yellow
    exit 0
}

# -------------------------------------------------------------------------
# 5️⃣ Deletion loop – wrapped in try / catch for per‑folder safety
# -------------------------------------------------------------------------
foreach ($folder in $foldersToDelete) {
    try {
        Write-Host "[DEL]   $folder ..." -NoNewline
        Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction Stop
        Write-Host ' done' -ForegroundColor Green
        Write-Log "Deleted folder: $folder" Green
    } catch {
        Write-Host ' ❌' -ForegroundColor Red
        Write-Log "Failed to delete $folder : $_" Red
    }
}

# -------------------------------------------------------------------------
# 6️⃣ Completion banner & next steps
# -------------------------------------------------------------------------
Write-Host ''
Write-Host '========================================' -ForegroundColor Green
Write-Host '   Reset Complete!'                -ForegroundColor Green
Write-Host '========================================' -ForegroundColor Green

if ($Mode -eq 'soft') {
    Write-Host ''
    Write-Host "Next step: run .\launch.bat to re‑download runtimes" -ForegroundColor Cyan
    Write-Host "Your API keys and config are still saved in $Root\data" -ForegroundColor Cyan
} else {
    Write-Host ''
    Write-Host "Next step: run .\launch.bat for a completely fresh start" -ForegroundColor Cyan
    Write-Host "You will need to re‑run the setup wizard and re‑enter API keys" -ForegroundColor Cyan
}

Write-Log "Reset script finished (Mode=$Mode)." Green
exit 0