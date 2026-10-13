<# =============================================================================
# Hermes Pendrive_X – Windows Portable Runtime Setup
# =============================================================================
# Downloads and extracts:
#   • Stand‑alone Python (3.11)
#   • Node.js 22 LTS
#   • uv (fast pip replacement)
#   • ripgrep
#   • optional MinGit
#   • Hermes source (main branch)
# Then creates a uv‑managed venv, installs dependencies (core + Telegram) and,
# if requested, Playwright browsers.
#
# New capabilities:
#   – –skip-git, –skip-playwright, –skip-uv, –dry-run, –launch
#   – timestamped log file (install.log)
#   – manifest.json with component versions
#   – strict PowerShell mode + deterministic error handling
#   – checksum verification (SHA‑256)
#   – clean‑up on Ctrl‑C / script exit
# =============================================================================
# Usage examples:
#   .\setup-windows.ps1 -Root C:\HermesPortable               # interactive
#   .\setup-windows.ps1 -Root $PWD -Skip-Git -Launch         # no Git, auto‑run
#   .\setup-windows.ps1 -Root $PWD -DryRun                    # preview only
# =============================================================================
# #>

[CmdletBinding(SupportsShouldProcess=$true, DefaultParameterSetName='Interactive')]
param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidatePattern('^[A-Za-z]:\\')]
    [string] $Root,

    [switch] $SkipGit,
    [switch] $SkipPlaywright,
    [switch] $SkipUv,
    [switch] $DryRun,
    [switch] $Launch   # If present, the script will start hermes.exe automatically
)

# -------------------------------------------------
# Strict mode and global preferences
# -------------------------------------------------
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -------------------------------------------------
# Logging helper (writes to console with colour *and* to a file)
# -------------------------------------------------
$LogFile = Join-Path $Root '.cache\runtimes\windows-x64\install.log'
function Log-Entry {
    param(
        [ValidateSet('INFO','WARN','ERROR')] [string] $Level,
        [string] $Message
    )
    $timestamp = Get-Date -UFormat "%Y-%m-%dT%H:%M:%SZ"
    $line = "[$timestamp] [$Level] $Message"
    # Write coloured console output
    switch ($Level) {
        'INFO' { Write-Host $Message -ForegroundColor Cyan }
        'WARN' { Write-Host $Message -ForegroundColor Yellow }
        'ERROR' { Write-Host $Message -ForegroundColor Red }
    }
    # Append plain line to the log file (no colour)
    $line | Out-File -FilePath $LogFile -Encoding utf8 -Append
}

# -------------------------------------------------
# Run‑command helper (log start/end + capture exit code)
# -------------------------------------------------
function Invoke-WithLog {
    param(
        [string] $Label,
        [scriptblock] $ScriptBlock
    )
    Log-Entry INFO "START $Label"
    try {
        & $ScriptBlock
        $rc = $LASTEXITCODE
        if ($rc -ne 0) { throw "exit code $rc" }
        Log-Entry INFO "DONE  $Label"
    }
    catch {
        Log-Entry ERROR "FAILED $Label – $_" 
        throw   # re‑throw so the outer script aborts (thanks to -e)
    }
}

# -------------------------------------------------
# Clean‑up trap – delete $TempDir on any exit
# -------------------------------------------------
$global:TempDir = $null
trap {
    if ($global:TempDir -and (Test-Path $global:TempDir)) {
        Remove-Item $global:TempDir -Recurse -Force -ErrorAction SilentlyContinue
        Log-Entry INFO "Removed temporary folder $TempDir"
    }
    # re‑throw the original error so callers see it
    throw $_
}

# -------------------------------------------------
# Version table & URLs (easy to bump)
# -------------------------------------------------
$Versions = @{
    python   = @{ tag='20241016'; version='3.11.10+20241016'; arch='x64'; ext='tar.gz'; url='https://github.com/indygreg/python-build-standalone/releases/download' }
    node     = @{ version='22.14.0'; url='https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip'; arch='x64' }
    uv       = @{ version='0.6.8'; url='https://github.com/astral-sh/uv/releases/download/0.6.8/uv-x86_64-pc-windows-msvc.zip'; arch='x64' }
    rg       = @{ version='14.1.1'; url='https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-pc-windows-msvc.zip'; arch='x64' }
    git      = @{ version='2.53.0.windows.1'; url='https://github.com/git-for-windows/git/releases/download/v2.53.0.windows.1/MinGit-2.53.0-64-bit.zip'; arch='x64' }
    hermes   = @{ url='https://github.com/NousResearch/hermes-agent/archive/refs/heads/main.zip'; commit='main' }
}

$IsInteractive = -not $PSCmdlet.MyInvocation.BoundParameters.ContainsKey('DryRun')

# -------------------------------------------------------------------------
# Path derivation (no hard‑coded leading "./")
# -------------------------------------------------------------------------
$CacheDir   = Join-Path $Root '.cache'
$RuntimeDir = Join-Path $CacheDir 'runtimes\windows-x64'
$BinDir     = Join-Path $RuntimeDir 'bin'
$SrcDir     = Join-Path $Root 'src'
$TempDir    = Join-Path $RuntimeDir '_temp'

# Ensure the basic tree exists (quietly)
New-Item -ItemType Directory -Force -Path $RuntimeDir,$SrcDir,$BinDir,$TempDir | Out-Null
$global:TempDir = $TempDir   # make it visible to the trap

# -------------------------------------------------------------------------
# First-run progress + cancellation handling (P2 UX)
# -------------------------------------------------------------------------
# setup-progress.json mirrors the Unix script so the Electron UI can show
# stages. setup-cancelled.flag marks an interrupted run; ready.flag is only
# written on full success so the next launch resumes recoverably. Logs are
# always preserved.
$ProgressFile   = Join-Path $RuntimeDir 'setup-progress.json'
$CancelledFlag  = Join-Path $RuntimeDir 'setup-cancelled.flag'
$ReadyFlagPath  = Join-Path $RuntimeDir 'ready.flag'
$global:SetupStage = 'starting'
$global:SetupPercent = 0
$global:SetupDone = $false
$SetupStageOrder = @('python','node','uv','rg','hermes-source','venv','python-deps','telegram-deps','security-deps','playwright','done')

function Write-SetupProgress {
    param([string]$Stage, [int]$Percent, [string]$Message)
    $global:SetupStage = $Stage
    $global:SetupPercent = $Percent
    $stages = @()
    $seen = $false
    foreach ($s in $SetupStageOrder) {
        $status = 'pending'
        if ($s -eq $Stage) { $status = 'active'; $seen = $true }
        elseif (-not $seen) { $status = 'done' }
        if ($global:SetupDone) { $status = 'done' }
        $stages += @{ name = $s; status = $status; done = ($status -eq 'done') }
    }
    $obj = @{
        stage = $Stage; percent = $Percent; message = $Message
        updated_at = (Get-Date -UFormat "%Y-%m-%dT%H:%M:%SZ"); stages = $stages
    }
    try { $obj | ConvertTo-Json -Depth 5 | Set-Content -Path $ProgressFile -Encoding utf8 } catch { }
}

function Write-CancelledState {
    param([string]$Reason)
    # Preserve logs; never leave a partial ready.flag behind.
    try { if (Test-Path $ReadyFlagPath) { Remove-Item $ReadyFlagPath -Force -ErrorAction SilentlyContinue } } catch { }
    try {
        @{ cancelled = $true; stage = $global:SetupStage; reason = $Reason; at = (Get-Date -UFormat "%Y-%m-%dT%H:%M:%SZ") } |
            ConvertTo-Json | Set-Content -Path $CancelledFlag -Encoding utf8
    } catch { }
    try { Write-SetupProgress -Stage $global:SetupStage -Percent $global:SetupPercent -Message "Cancelled at $($global:SetupStage): $Reason Logs preserved — re-run setup to resume." } catch { }
    try { Log-Entry WARN "Setup cancelled at stage $($global:SetupStage): $Reason Logs preserved; next launch will resume (recoverable state)." } catch { }
}

# Fresh attempt clears any stale cancellation marker (re-created only on failure).
try { if (Test-Path $CancelledFlag) { Remove-Item $CancelledFlag -Force -ErrorAction SilentlyContinue } } catch { }

# Ctrl-C / console cancel: record a recoverable cancelled state instead of a corrupt half-install.
try {
    [Console]::TreatControlCAsInput = $false
    [Console]::CancelKeyPress += {
        param($sender, $e)
        $e.Cancel = $true
        Write-CancelledState -Reason 'Ctrl-C pressed.'
    }
} catch { }

# -------------------------------------------------------------------------
# Helper – Download a file (curl > Invoke‑WebRequest > fallback)
# -------------------------------------------------------------------------
function Download-File {
    param(
        [Parameter(Mandatory)][string] $Url,
        [Parameter(Mandatory)][string] $OutFile,
        [hashtable] $KnownHashes   # optional: SHA256 -> true
    )
    $fileName = Split-Path $Url -Leaf

    if (Test-Path $OutFile) {
        $size = (Get-Item $OutFile).Length
        if ($size -gt 0) {
            $sizeMB = [math]::Round($size / 1MB, 2)
            Log-Entry INFO "$fileName already cached ($sizeMB MB)."
            if ($KnownHashes -and $KnownHashes.ContainsKey($fileName)) {
                $hash = Get-FileHash -Path $OutFile -Algorithm SHA256 | Select-Object -ExpandProperty Hash
                if ($hash -ne $KnownHashes[$fileName]) {
                    Log-Entry WARN "Checksum mismatch for $fileName – re‑downloading."
                    Remove-Item $OutFile -Force
                }
            }
            return
        }
        else {
            Log-Entry WARN "$fileName exists but is 0 bytes – re‑downloading."
            Remove-Item $OutFile -Force
        }
    }

    Log-Entry INFO "Downloading $fileName ..."
    # Preferred: native curl (built‑in to Windows 10+)
    $downloaded = $false
    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        $curlArgs = @('-L','-f','--retry',3,'--connect-timeout',30,'--max-time',600,'-o',$OutFile,$Url)
        & curl.exe @curlArgs
        if ($LASTEXITCODE -eq 0) { $downloaded = $true }
    }

    if (-not $downloaded) {
        $ProgressPreference = 'Continue'  # keep progress bar visible
        try {
            Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 600
        }
        catch {
            throw "Download of $Url failed: $_"
        }
        finally {
            $ProgressPreference = 'SilentlyContinue'
        }
    }

    if (-not (Test-Path $OutFile)) {
        throw "Download succeeded but file not found at $OutFile"
    }
    $finalSize = (Get-Item $OutFile).Length
    if ($finalSize -eq 0) {
        Remove-Item $OutFile -Force -ErrorAction SilentlyContinue
        throw "Downloaded file is empty: $fileName"
    }
    $sizeMB = [math]::Round($finalSize / 1MB, 2)
    Log-Entry INFO "Download complete: $sizeMB MB."
}

# -------------------------------------------------------------------------
# Helper – Extract given archive type (ZIP or .tar.gz)
# -------------------------------------------------------------------------
function Extract-Archive {
    param(
        [Parameter(Mandatory)][string] $Archive,
        [Parameter(Mandatory)][string] $Destination
    )
    $label = Split-Path $Archive -Leaf
    Log-Entry INFO "Extracting $label ..."
    # Clean any previous incomplete attempt first
    if (Test-Path $Destination) {
        Remove-Item $Destination -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    # Detect type
    if ($Archive -match '\.zip$') {
        # Prefer PowerShell's Expand‑Archive (built‑in, works everywhere)
        try { Expand-Archive -Path $Archive -DestinationPath $Destination -Force -ErrorAction Stop }
        catch {
            # Fallback to native tar if Expand‑Archive fails (rare)
            Log-Entry WARN "Expand‑Archive failed – trying tar.exe."
            $t = Get-Command tar.exe -ErrorAction SilentlyContinue
            if ($t) {
                & tar.exe -xf $Archive -C $Destination
                if ($LASTEXITCODE -ne 0) { throw "tar.exe extraction failed for $label" }
            }
            else { throw "No archive extractor available." }
        }
    }
    else {
        # Assume .tar.gz or .tgz
        $t = Get-Command tar.exe -ErrorAction SilentlyContinue
        if (-not $t) { throw "tar.exe not found – cannot extract .tar.gz archives." }
        & tar.exe -xzf $Archive -C $Destination --strip-components=1
        if ($LASTEXITCODE -ne 0) { throw "tar extraction failed for $label (exit $LASTEXITCODE)" }
    }
    Log-Entry INFO "Extraction of $label completed."
}

# -------------------------------------------------------------------------
# Helper – Link a runtime binary into $BinDir (overwrites existing)
# -------------------------------------------------------------------------
function Ensure-BinLink {
    param(
        [Parameter(Mandatory)][string] $SourceBinPath,
        [Parameter(Mandatory)][string] $LinkName
    )
    $target = Join-Path $BinDir $LinkName
    if (Test-Path $target) { Remove-Item $target -Force }
    try {
        New-Item -ItemType SymbolicLink -Path $target -Target $SourceBinPath -ErrorAction Stop | Out-Null
        Log-Entry INFO "Linked $LinkName → $SourceBinPath"
    }
    catch {
        # Developer Mode / admin rights missing (typical on USB sticks): copy instead.
        Copy-Item -LiteralPath $SourceBinPath -Destination $target -Force
        Log-Entry WARN "Symlink unavailable for $LinkName – copied file instead."
    }
}

# -------------------------------------------------------------------------
# Helper – Generate a JSON manifest with version info
# -------------------------------------------------------------------------
function Write-Manifest {
    param(
        [hashtable] $ComponentInfo
    )
    $manifestPath = Join-Path $RuntimeDir 'manifest.json'
    $obj = @{ generated_at = (Get-Date -UFormat "%Y-%m-%dT%H:%M:%SZ"); versions = $ComponentInfo }
    $obj | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding utf8
    Log-Entry INFO "Wrote manifest to $manifestPath"
}

# -------------------------------------------------------------------------
# Helper – Read existing JSON manifest
# -------------------------------------------------------------------------
function Read-Manifest {
    $manifestPath = Join-Path $RuntimeDir 'manifest.json'
    if (Test-Path $manifestPath) {
        try {
            $json = Get-Content $manifestPath -Raw | ConvertFrom-Json
            if ($json.versions) { return $json.versions }
            return $json
        } catch {
            Log-Entry WARN "Failed to parse manifest.json – assuming empty."
            return $null
        }
    }
    return $null
}

if ($DryRun) {
    Log-Entry INFO "[DRY-RUN] Would install: Python $($Versions['python'].version), Node $($Versions['node'].version), uv $($Versions['uv'].version), Hermes source."
    Log-Entry INFO "[DRY-RUN] No changes were made. Re-run without -DryRun to install."
    return
}

$CurrentManifest = Read-Manifest

try {
# -------------------------------------------------------------------------
# 1️⃣ Portable Python
# -------------------------------------------------------------------------
function Install-Python {
    $info = $Versions['python']
    if ($CurrentManifest -and $CurrentManifest.python -eq $info.version -and (Test-Path (Join-Path $RuntimeDir 'python'))) {
        Log-Entry INFO "Python $($info.version) already installed. Skipping."
        return
    }
    $archive = Join-Path $RuntimeDir "python.$($info.ext)"
    $cpuArch = if ($info.arch -eq 'x64') { 'x86_64' } else { $info.arch }
    $dest = Join-Path $RuntimeDir 'python'
    Download-File -Url "$($info.url)/$($info.tag)/cpython-$($info.version)-$cpuArch-pc-windows-msvc-install_only.$($info.ext)" -OutFile $archive
    Extract-Archive -Archive $archive -Destination $dest
    Ensure-BinLink -SourceBinPath (Join-Path $dest 'python.exe') -LinkName 'python.exe'
    Log-Entry INFO "Python $($info.version) installed."
}
Write-SetupProgress -Stage 'python' -Percent 5 -Message 'Downloading Python runtime…'
Install-Python

# -------------------------------------------------------------------------
# 2️⃣ Node.js
# -------------------------------------------------------------------------
function Install-Node {
    $info = $Versions['node']
    if ($CurrentManifest -and $CurrentManifest.node -eq $info.version -and (Test-Path (Join-Path $RuntimeDir 'node'))) {
        Log-Entry INFO "Node.js $($info.version) already installed. Skipping."
        return
    }
    $archive = Join-Path $RuntimeDir "node.$($info.url | Split-Path -Leaf)"
    $dest  = Join-Path $RuntimeDir 'node'
    Download-File -Url $info.url -OutFile $archive
    Extract-Archive -Archive $archive -Destination $dest
    $nodeExe = Join-Path $dest 'node.exe'
    if (-not (Test-Path $nodeExe)) {
        $nested = Get-ChildItem $dest -Recurse -Filter 'node.exe' | Select-Object -First 1
        if ($nested) {
            Get-ChildItem $dest -Directory | Select-Object -First 1 | ForEach-Object {
                Get-ChildItem $_.FullName | Move-Item -Destination $dest -Force
                Remove-Item $_.FullName -Force
            }
            $nodeExe = Join-Path $dest 'node.exe'
        }
    }
    if (Test-Path $nodeExe) {
        Ensure-BinLink -SourceBinPath $nodeExe -LinkName 'node.exe'
    } else {
        Log-Entry WARN "node.exe not found after extraction."
    }
    Log-Entry INFO "Node.js $($info.version) installed."
}
Write-SetupProgress -Stage 'node' -Percent 20 -Message 'Downloading Node.js…'
Install-Node

# -------------------------------------------------------------------------
# 3️⃣ uv (optional)
# -------------------------------------------------------------------------
function Install-Uv {
    $info = $Versions['uv']
    if ($CurrentManifest -and $CurrentManifest.uv -eq $info.version -and (Test-Path (Join-Path $RuntimeDir 'uv'))) {
        Log-Entry INFO "uv $($info.version) already installed. Skipping."
        return
    }
    $archive = Join-Path $RuntimeDir "uv.$($info.url | Split-Path -Leaf)"
    $dest = Join-Path $RuntimeDir 'uv'
    Download-File -Url $info.url -OutFile $archive
    Extract-Archive -Archive $archive -Destination $dest
    Ensure-BinLink -SourceBinPath (Join-Path $dest 'uv.exe') -LinkName 'uv.exe'
    Log-Entry INFO "uv $($info.version) installed."
}
Write-SetupProgress -Stage 'uv' -Percent 32 -Message 'Installing uv…'
if (-not $SkipUv) { Install-Uv }

# -------------------------------------------------------------------------
# 4️⃣ ripgrep
# -------------------------------------------------------------------------
function Install-Rg {
    $info = $Versions['rg']
    if ($CurrentManifest -and $CurrentManifest.rg -eq $info.version -and (Test-Path (Join-Path $RuntimeDir 'rg'))) {
        Log-Entry INFO "ripgrep $($info.version) already installed. Skipping."
        return
    }
    $archive = Join-Path $RuntimeDir "rg.$($info.url | Split-Path -Leaf)"
    $dest = Join-Path $RuntimeDir 'rg'
    Download-File -Url $info.url -OutFile $archive
    Extract-Archive -Archive $archive -Destination $dest
    # The binary lives directly as rg.exe inside the extracted folder
    $rgExe = Get-ChildItem $dest -Recurse -Filter 'rg.exe' | Select-Object -First 1
    if ($rgExe) {
        Ensure-BinLink -SourceBinPath $rgExe.FullName -LinkName 'rg.exe'
        Log-Entry INFO "ripgrep $($info.version) installed."
    }
    else {
        Log-Entry WARN "ripgrep binary not found after extraction."
    }
}
Write-SetupProgress -Stage 'rg' -Percent 40 -Message 'Installing ripgrep…'
Install-Rg

# -------------------------------------------------------------------------
# 5️⃣ Git (MinGit) – completely optional
# -------------------------------------------------------------------------
function Install-Git {
    $info = $Versions['git']
    if ($CurrentManifest -and $CurrentManifest.git -eq $info.version -and (Test-Path (Join-Path $RuntimeDir 'git'))) {
        Log-Entry INFO "Git $($info.version) already installed. Skipping."
        return
    }
    $archive = Join-Path $RuntimeDir "git.$($info.url | Split-Path -Leaf)"
    $dest = Join-Path $RuntimeDir 'git'
    try {
        Download-File -Url $info.url -OutFile $archive
        Extract-Archive -Archive $archive -Destination $dest
        Ensure-BinLink -SourceBinPath (Join-Path $dest 'cmd\git.exe') -LinkName 'git.exe'
        Log-Entry INFO "Git $($info.version) installed."
    }
    catch {
        if ($PSCmdlet.ShouldProcess($null,$null)) { throw }
        Log-Entry WARN "Git installation failed – continuing without it."
    }
}
if (-not $SkipGit) { Install-Git }

# -------------------------------------------------------------------------
# 6️⃣ Hermes source (main branch)
# -------------------------------------------------------------------------
function Install-HermesSource {
    $info = $Versions['hermes']
    $finalSrc = Join-Path $SrcDir 'hermes-agent'
    
    # Delta Update check: if .git exists, use git pull
    if (Test-Path (Join-Path $finalSrc '.git')) {
        Log-Entry INFO "Hermes source is a Git repo. Attempting delta update (git pull)..."
        $gitExe = Join-Path $BinDir 'git.exe'
        if (-not (Test-Path $gitExe)) { $gitExe = 'git' }
        
        try {
            Set-Location $finalSrc
            & $gitExe pull
            Log-Entry INFO "Hermes source updated via Git."
            return
        } catch {
            Log-Entry WARN "Git pull failed. Falling back to ZIP download."
            Set-Location $Root
        }
    }

    $archive = Join-Path $RuntimeDir "source.$($info.url | Split-Path -Leaf)"
    $destTemp = Join-Path $TempDir 'source'
    Download-File -Url $info.url -OutFile $archive
    Extract-Archive -Archive $archive -Destination $destTemp
    # The zip contains a folder named “hermes‑agent‑<hash>”
    $srcSub = Get-ChildItem $destTemp -Directory | Select-Object -First 1
    if (-not $srcSub) { throw "Hermes source archive does not contain a sub‑folder." }
    
    if (Test-Path $finalSrc) { Remove-Item $finalSrc -Recurse -Force }
    Move-Item -LiteralPath $srcSub.FullName -Destination $finalSrc -Force
    Log-Entry INFO "Hermes source extracted to $finalSrc"
}
Write-SetupProgress -Stage 'hermes-source' -Percent 50 -Message 'Fetching Hermes source…'
Install-HermesSource

# -------------------------------------------------------------------------
# 7️⃣ Create a uv‑managed virtual environment
# -------------------------------------------------------------------------
function Create-Venv {
    $pythonExe = Join-Path $RuntimeDir 'python\python.exe'
    $uvExe     = Join-Path $RuntimeDir 'uv\uv.exe'
    $venvDir   = Join-Path $RuntimeDir 'venv'

    if (-not (Test-Path $pythonExe)) { throw "Python executable not found at $pythonExe" }
    if (-not (Test-Path $uvExe)) { throw "uv executable not found at $uvExe – run Install‑Uv first." }

    Log-Entry INFO "Creating virtual environment with uv..."
    $null = & $uvExe venv $venvDir --python $pythonExe   # $null because uv writes to stdout
    if ($LASTEXITCODE -ne 0) { throw "uv venv creation failed (exit $LASTEXITCODE)." }

    # Add the venv's Scripts folder to the PATH for the rest of this script
    $env:Path += ";$venvDir\Scripts"
    Log-Entry INFO "Virtual environment at $venvDir is ready."
}
Write-SetupProgress -Stage 'venv' -Percent 62 -Message 'Creating virtual environment…'
Create-Venv

# -------------------------------------------------------------------------
# 8️⃣ Install core Python dependencies (editable + extras)
# -------------------------------------------------------------------------
function Install-PythonDeps {
    $venvPython = Join-Path $RuntimeDir 'venv\Scripts\python.exe'
    $uvExe      = Join-Path $RuntimeDir 'uv\uv.exe'
    $srcPackage = Join-Path $SrcDir 'hermes-agent'

    # Build the -e argument with the [all] extra (single pip spec)
    $editableArgs = @("-e", "$srcPackage[all]")

    Log-Entry INFO "Installing core Python deps (uv pip preferred)..."
    $pipCmd = {
        & $uvExe pip install --python $venvPython --link-mode=copy @editableArgs
    }
    try {
        Invoke-WithLog -Label "uv pip install" -ScriptBlock $pipCmd
    }
    catch {
        Log-Entry WARN "uv pip failed – falling back to pip."
        # Ensure pip is present (uv's venv always bundles it)
        $pipCmd = {
            & $venvPython -m pip install -e "$srcPackage[all]"
        }
        Invoke-WithLog -Label "pip install (fallback)" -ScriptBlock $pipCmd
    }
}
Write-SetupProgress -Stage 'python-deps' -Percent 70 -Message 'Installing core Python dependencies…'
Install-PythonDeps

# -------------------------------------------------------------------------
# 9️⃣ Install messaging dependencies (Telegram)
# -------------------------------------------------------------------------
function Install-MessagingDeps {
    $venvPython = Join-Path $RuntimeDir 'venv\Scripts\python.exe'
    $uvExe      = Join-Path $RuntimeDir 'uv\uv.exe'

    Log-Entry INFO "Installing python‑telegram‑bot (extra)..."
    $msg = {
        & $uvExe pip install --python $venvPython --link-mode=copy "python-telegram-bot[webhooks]==22.6"
    }
    try {
        Invoke-WithLog -Label "uv pip telegram" -ScriptBlock $msg
        Log-Entry INFO "Telegram deps installed via uv."
    }
    catch {
        Log-Entry WARN "uv install for telegram‑bot failed – trying pip."
        & $venvPython -m pip install "python-telegram-bot[webhooks]==22.6"
        Log-Entry INFO "Telegram deps installed via pip."
    }
}
Write-SetupProgress -Stage 'telegram-deps' -Percent 80 -Message 'Installing messaging dependencies…'
Install-MessagingDeps

# -------------------------------------------------------------------------
# Install Security Dependencies (Encryption & Hardware Tokens)
# -------------------------------------------------------------------------
function Install-SecurityDeps {
    $venvPython = Join-Path $RuntimeDir 'venv\Scripts\python.exe'
    $uvExe      = Join-Path $RuntimeDir 'uv\uv.exe'

    Log-Entry INFO "Installing security dependencies (cryptography, yubikey-manager)..."
    $sec = {
        & $uvExe pip install --python $venvPython --link-mode=copy `
            "cryptography>=41.0.0" `
            "yubikey-manager>=5.0.0"
    }
    try {
        Invoke-WithLog -Label "uv pip security" -ScriptBlock $sec
        Log-Entry INFO "Security deps installed via uv."
    }
    catch {
        Log-Entry WARN "uv install for security deps failed – trying pip."
        & $venvPython -m pip install `
            "cryptography>=41.0.0" `
            "yubikey-manager>=5.0.0"
        Log-Entry INFO "Security deps installed via pip."
    }
}
Write-SetupProgress -Stage 'security-deps' -Percent 88 -Message 'Installing security dependencies…'
Install-SecurityDeps

# -------------------------------------------------------------------------
#  Install Playwright browsers (optional)
# -------------------------------------------------------------------------
function Install-Playwright {
    $venvPython = Join-Path $RuntimeDir 'venv\Scripts\python.exe'

    Log-Entry INFO "Installing Playwright browsers (Chromium)..."
    try {
        $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $RuntimeDir 'playwright'
        & $venvPython -m playwright install chromium
        Log-Entry INFO "Playwright browsers installed."
    }
    catch {
        Log-Entry WARN "Playwright installation failed – web‑tools will be limited."
    }
}
Write-SetupProgress -Stage 'playwright' -Percent 94 -Message 'Installing Playwright browsers…'
if (-not $SkipPlaywright) { Install-Playwright }

# -------------------------------------------------------------------------
# 📦 Mark the runtime as ready + write manifest (only on full success)
# -------------------------------------------------------------------------
$readyFlag = Join-Path $RuntimeDir 'ready.flag'
"" | Set-Content -Path $readyFlag -Encoding utf8
Log-Entry INFO "Created $readyFlag"

# Build a quick manifest that mirrors the Unix version
$manifestInfo = @{
    python   = $Versions['python'].version
    node     = $Versions['node'].version
    uv       = $Versions['uv'].version
    rg       = $Versions['rg'].version
    git      = if ($SkipGit) { $null } else { $Versions['git'].version }
    hermes   = $Versions['hermes'].commit
    playwright = if ($SkipPlaywright) { $null } else { 'Chromium' }
}
Write-Manifest -ComponentInfo $manifestInfo
$global:SetupDone = $true
Write-SetupProgress -Stage 'done' -Percent 100 -Message 'Setup completed.'

# -------------------------------------------------------------------------
# 🧹 Final cleanup (temp dir was removed by the trap)
# -------------------------------------------------------------------------
Log-Entry INFO "Runtime setup completed."
} catch {
    $msg = $_.Exception.Message
    Log-Entry ERROR "Setup failed at stage $($global:SetupStage): $msg Logs preserved at $LogFile."
    Write-CancelledState -Reason $msg
    throw
}

# -------------------------------------------------------------------------
# 🚀 Optional auto‑launch
# -------------------------------------------------------------------------
if ($Launch) {
    $hermesExe = Join-Path $RuntimeDir 'venv\Scripts\hermes.exe'
    if (Test-Path $hermesExe) {
        Log-Entry INFO "Auto‑launching hermes.exe ..."
        # Replace the PowerShell process so the hermes console is the foreground process
        & $hermesExe
    }
    else {
        Log-Entry WARN "Hermes executable not found – launch aborted."
    }
}
else {
    # Show a short “next step” banner (mirrors the Unix script)
    Write-Host "`n========================================" -ForegroundColor Green
    Write-Host "   Hermes Pendrive_X – Setup Complete!" -ForegroundColor Green
    Write-Host "========================================`n"
    Write-Host "To start the agent, run:" -ForegroundColor Cyan
    Write-Host "   $RuntimeDir\venv\Scripts\hermes.exe" -ForegroundColor Cyan
    Write-Host "`nOr launch the bundled `launch.bat` which does the same work." -ForegroundColor Cyan
}