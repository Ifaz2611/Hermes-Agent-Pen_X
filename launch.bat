@echo off
::======================================================================
:: Hermes Agent – Pendrive_X (Windows launcher)
::======================================================================
:: Portable, isolated entry point for the Hermes AI Agent.
::======================================================================
:: Features retained:
::   • First‑run runtime download (Python, Node, uv, rg, Git)
::   • Environment isolation (PATH, PYTHON*, UV*, PLAYWRIGHT_BROWSERS_PATH)
::   • Interactive colour‑coded dashboard
::   • Advanced options (Doctor, Logs, Config, Restart, Update)
::======================================================================
:: New goodies:
::   • Safer argument handling (SHIFT)
::   • Centralised colour & error helpers
::   • ANSI‑escape fallback for older Windows
::   • Optional /silent mode for CI
::======================================================================

setlocal EnableDelayedExpansion
:: -------------------------------------------------------------------
:: 0. Helper helpers – colour & error logging
:: -------------------------------------------------------------------
if errorlevel 1 (rem trick – will be ignored, just keep setlocal alive)

:: -------------------------------------------------------------------
:: 0a. Detect ESC character (works on Windows 10+ and falls back)
:: -------------------------------------------------------------------
for /f "tokens=1" %%a in ('prompt $E ^| cmd') do set "ESC=%%a"
if not defined ESC set "ESC="   & rem classic ESC for older cmd

:: colour macros (they just expand to the ESC string + code)
set "RST=%ESC%[0m"
set "BOLD=%ESC%[1m"
set "DIM=%ESC%[2m"
set "RED=%ESC%[31m"
set "GRN=%ESC%[32m"
set "YEL=%ESC%[33m"
set "BLU=%ESC%[34m"
set "MAG=%ESC%[35m"
set "CYN=%ESC%[36m"
set "WHT=%ESC%[37m"
set "BRD=%ESC%[90m"
set "BRC=%ESC%[92m"
set "BRE=%ESC%[93m"
set "BRM=%ESC%[94m"
set "BRY=%ESC%[95m"
set "BRG=%ESC%[96m"
set "BGB=%ESC%[44m%ESC%[97m"
set "BGC=%ESC%[46m%ESC%[30m"

:: -------------------------------------------------------------------
:: 0b. Centralised error printer (subroutine - must be skipped on fallthrough)
:: -------------------------------------------------------------------
goto :after_MkErr
:MkErr
echo %RED%[ERROR]%RST% %~1
exit /b 1
:after_MkErr
:: -------------------------------------------------------------------

:: -------------------------------------------------------------------
:: 1. Resolve portable root (trailing \ removed, spaces safe)
:: -------------------------------------------------------------------
set "PORTABLE_ROOT=%~dp0"
rem Remove trailing backslash (works even if there is none)
if "%PORTABLE_ROOT:~-1%"=="\" set "PORTABLE_ROOT=%PORTABLE_ROOT:~0,-1%"

:: -------------------------------------------------------------------
:: 2. Core folder layout
:: -------------------------------------------------------------------
set "HERMES_HOME=%PORTABLE_ROOT%\data"
set "CACHE_DIR=%PORTABLE_ROOT%\.cache"
set "RUNTIME_DIR=%CACHE_DIR%\runtimes\windows-x64"
set "SRC_DIR=%PORTABLE_ROOT%\src"
set "VENV_DIR=%RUNTIME_DIR%\venv"

:: -------------------------------------------------------------------
:: 3. Parse arguments (Silent, RAM Disk, Profile)
:: -------------------------------------------------------------------
set "SILENT=0"
set "USE_RAMDISK=0"
set "PROFILE_NAME="

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="/silent" (
    set "SILENT=1"
    shift
    goto :parse_args
)
if /I "%~1"=="/ramdisk" (
    set "USE_RAMDISK=1"
    shift
    goto :parse_args
)
if /I "%~1"=="/profile" (
    set "PROFILE_NAME=%~2"
    if not defined PROFILE_NAME (
        call :MkErr "Profile name not specified after /profile."
    )
    shift
    shift
    goto :parse_args
)
:args_done

:: Update HERMES_HOME if profile is specified
set "HERMES_HOME=%PORTABLE_ROOT%\data"
if defined PROFILE_NAME (
    set "HERMES_HOME=%PORTABLE_ROOT%\data\profiles\%PROFILE_NAME%"
    if %SILENT%==0 echo %BRM%[PROFILE]%RST% Active Profile: %MAG%!PROFILE_NAME!%RST%
)

:: -------------------------------------------------------------------
:: 4. First‑run runtime download (Always against USB root)
:: -------------------------------------------------------------------
if not exist "%RUNTIME_DIR%\ready.flag" (
    if %SILENT%==0 (
        echo.
        echo %BGB% HERMES Pendrive_X – First‑Run Setup %RST%
        echo %BGB%    ~600 MB of runtimes will be downloaded. %RST%
        echo.
    )
    powershell -NoProfile -ExecutionPolicy Bypass ^
        -Command "& { .\scripts\setup-windows.ps1 -Root \"%PORTABLE_ROOT%\" }" ^
        2>&1 | findstr /V "^$"
    if errorlevel 1 (
        call :MkErr "Runtime‑setup script failed (exit %ERRORLEVEL%). Abort."
    )
)

:: -------------------------------------------------------------------
:: 5. RAM Disk / Read-Only Mode Optimization
:: -------------------------------------------------------------------
if %USE_RAMDISK%==1 (
    echo %CYN%[PERF]%RST% RAM Disk mode enabled.
    set "RAMDISK_ROOT=%TEMP%\hermes_ramdisk"
    
    :: We want to copy .cache and src, but NOT data (persistence on USB)
    if not exist "!RAMDISK_ROOT!" mkdir "!RAMDISK_ROOT!"
    
    echo %CYN%[PERF]%RST% Syncing runtime to local temp (speed boost)...
    
    :: Copy .cache (runtimes)
    if not exist "!RAMDISK_ROOT!\.cache\runtimes\windows-x64\ready.flag" (
        echo %CYN%[PERF]%RST% Copying .cache (this may take 30-60s on USB 2.0)...
        if not exist "!RAMDISK_ROOT!\.cache" mkdir "!RAMDISK_ROOT!\.cache"
        xcopy "%CACHE_DIR%\*" "!RAMDISK_ROOT!\.cache\" /E /I /H /Y /Q >nul
    )

    :: Copy src
    if not exist "!RAMDISK_ROOT!\src\hermes-agent" (
        echo %CYN%[PERF]%RST% Copying src...
        if not exist "!RAMDISK_ROOT!\src" mkdir "!RAMDISK_ROOT!\src"
        xcopy "%SRC_DIR%\*" "!RAMDISK_ROOT!\src\" /E /I /H /Y /Q >nul
    )

    :: Redirect paths to RAM disk for this session
    set "CACHE_DIR=!RAMDISK_ROOT!\.cache"
    set "RUNTIME_DIR=!CACHE_DIR!\runtimes\windows-x64"
    set "SRC_DIR=!RAMDISK_ROOT!\src"
    set "VENV_DIR=!RUNTIME_DIR!\venv"

    :: Fix venv path in pyvenv.cfg (absolute paths in venv need to point to RAM disk)
    if exist "!VENV_DIR!\pyvenv.cfg" (
        powershell -NoProfile -Command "(Get-Content '!VENV_DIR!\pyvenv.cfg') -replace '^home = .*', 'home = !RUNTIME_DIR!\python' | Set-Content '!VENV_DIR!\pyvenv.cfg'"
    )
)

:: -------------------------------------------------------------------
:: 6. Activate the portable venv (keeps PATH tidy)
:: -------------------------------------------------------------------
call "%VENV_DIR%\Scripts\activate.bat" >nul 2>&1
if errorlevel 1 (
    call :MkErr "Failed to activate virtual environment."
)

:: -------------------------------------------------------------------
:: 5.5. Unlock encrypted data vault (if encrypted)
:: -------------------------------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass ^
    -Command "& { .\scripts\unlock-vault.ps1 -DataDir \"%HERMES_HOME%\" -PythonExe \"python\" }" ^
    2>&1
if errorlevel 1 (
    call :MkErr "Failed to unlock vault or user cancelled."
)

:: -------------------------------------------------------------------
:: 6. Verify source exists
:: -------------------------------------------------------------------
if not exist "%SRC_DIR%\hermes-agent" (
    call :MkErr "Hermes source missing at %SRC_DIR%\hermes-agent. Delete %CACHE_DIR% and retry."
)

:: -------------------------------------------------------------------
:: 7. Argument forwarding (handles “hermes setup” pattern)
:: NOTE: no GOTO labels inside parenthesised blocks - batch cannot handle it.
:: -------------------------------------------------------------------
set "ARGS="
if not "%~1"=="" (
    if /I "%~1"=="hermes" (
        shift
    )
    if /I "%~1"=="mcp" (
        shift
        call :RunMcp %*
        exit /b %ERRORLEVEL%
    )
    if /I "%~1"=="profile" (
        shift
        call :RunProfile %*
        exit /b %ERRORLEVEL%
    )
    if not "%~1"=="" (
        call :RunHermes %*
        exit /b %ERRORLEVEL%
    )
)
goto :status_detect
:RunMcp
python "%PORTABLE_ROOT%\tools\mcp\mcp_manager.py" %*
exit /b %ERRORLEVEL%
:RunProfile
python "%PORTABLE_ROOT%\tools\profiles\profile_manager.py" %*
exit /b %ERRORLEVEL%
:RunHermes
hermes %*
exit /b %ERRORLEVEL%
:status_detect

:: -------------------------------------------------------------------
:: 8. Gather status variables (single block)
:: -------------------------------------------------------------------
set "SETUP_STATUS=Not configured"
set "SETUP_ICON=[ ]"
set "SETUP_COLOR=%RED%"
set "PROVIDER_NAME="
set "MODEL_NAME="
set "GATEWAY_STATUS=Stopped"
set "GATEWAY_ICON=[ ]"
set "GATEWAY_COLOR=%DIM%"
set "GATEWAY_PID="

:: .env sanity check - any non-comment KEY=VALUE line means configured
set "SETUP_STATUS=Not configured"
set "SETUP_ICON=[ ]"
set "SETUP_COLOR=%RED%"
if exist "%HERMES_HOME%\.env" (
    findstr /R /C:"^[A-Z][A-Za-z0-9_]*=" "%HERMES_HOME%\.env" >nul 2>&1
    if not errorlevel 1 (
        set "SETUP_STATUS=Configured"
        set "SETUP_ICON=[OK]"
        set "SETUP_COLOR=%GRN%"
    )
)
:dotenv_done

:: provider & model from config.yaml (accepts single, double or no quotes)
set "PROVIDER_NAME="
set "MODEL_NAME="
if exist "%HERMES_HOME%\config.yaml" (
    for /f "tokens=1,* delims==" %%A in ('powershell -NoProfile -Command "$h = Get-Content '%HERMES_HOME%\config.yaml' -Raw; $p = [System.Text.RegularExpressions.Regex]::Match($h,'provider\s*:\s*[''\"\s]*([^''\"\r\n]+)'); $m = [System.Text.RegularExpressions.Regex]::Match($h,'default\s*:\s*[''\"\s]*([^''\"\r\n]+)'); if ($p.Success) { Write-Host ('PROVIDER=' + $p.Groups[1].Value.Trim()) }; if ($m.Success) { Write-Host ('MODEL=' + $m.Groups[1].Value.Trim()) }"') do (
        if "%%A"=="PROVIDER" set "PROVIDER_NAME=%%B"
        if "%%A"=="MODEL" set "MODEL_NAME=%%B"
    )
)

:: gateway PID file handling
if exist "%HERMES_HOME%\gateway.pid" (
    for /f "usebackq delims=" %%A in ("%HERMES_HOME%\gateway.pid") do (
        set "GATEWAY_PID=%%A"
        set "GATEWAY_STATUS=Running (PID !GATEWAY_PID!)"
        set "GATEWAY_ICON=[OK]"
        set "GATEWAY_COLOR=%GRN%"
    )
)

:: hermes version (tolerant of single or double quotes; empty when unknown)
set "HERMES_VERSION=unknown"
if exist "%SRC_DIR%\hermes-agent\hermes_cli\__init__.py" (
    for /f "tokens=2 delims==\"'" %%V in ('powershell -NoProfile -Command "$t = Get-Content '%SRC_DIR%\hermes-agent\hermes_cli\__init__.py' -Raw; $m = [System.Text.RegularExpressions.Regex]::Match($t,'__version__\s*=\s*[''\"]([^''\"]+)'); if ($m.Success) { Write-Host ('VER=' + $m.Groups[1].Value) }" ^| findstr VER') do set "HERMES_VERSION=%%V"
)

:: -------------------------------------------------------------------
9. UI Functions (jump over subroutines on first pass) (colour‑aware echo, menu, etc.)
:: -------------------------------------------------------------------
goto :ShowMainMenu
:DashLine
echo %BRC%------------------------------------------------------------%RST%
exit /b 0

:ShowMainMenu
cls
call :DashLine
echo %BRG% HERMES AGENT – PENDRIVE_X  v%HERMES_VERSION% %RST%
echo %BGC% Portable, Isolated AI Agent Environment %RST%
call :DashLine
echo.
echo %CYN%--- SYSTEM STATUS %RST%
echo   %DIM%Setup   %RST% !SETUP_COLOR!!SETUP_ICON!%RST% %WHT%!SETUP_STATUS!%RST%
if defined PROVIDER_NAME echo   %DIM%Provider %RST% %CYN%!PROVIDER_NAME!%RST%
if defined MODEL_NAME    echo   %DIM%Model    %RST% %WHT%!MODEL_NAME!%RST%
echo   %DIM%Gateway  %RST% !GATEWAY_COLOR!!GATEWAY_ICON!%RST% %WHT%!GATEWAY_STATUS!%RST%
echo.
echo %CYN%--- MAIN ACTIONS %RST%
echo  %YEL%[1]%RST%  %WHT%Start Hermes Chat%RST%           %DIM%-> Interactive CLI%RST%
echo  %YEL%[2]%RST%  %WHT%Setup / Reconfigure%RST%         %DIM%-> Provider & model%RST%
if "!GATEWAY_STATUS!"=="Running (PID !GATEWAY_PID!)" (
    echo  %YEL%[3]%RST%  %WHT%Stop Gateway%RST%            %DIM%-> %RED%[Currently Live]%RST%
) else (
    echo  %YEL%[3]%RST%  %WHT%Start Gateway%RST%           %DIM%-> Run API server in background%RST%
)
echo  %YEL%[4]%RST%  %WHT%Advanced Options%RST%         %DIM%-> Doctor, Logs, Config, Update%RST%
echo  %YEL%[5]%RST%   %BGB%Exit Launcher%RST%           %DIM%-> Close this window%RST%
call :DashLine
echo %WHT%Select an option (1‑5):%RST%
choice /C 12345 /N /M "Your choice:"
set "choice=%ERRORLEVEL%"

:: ---------------------------------------------------
:: 10. Main‑menu dispatch
:: ---------------------------------------------------
if %choice%==5 goto :EofExit
if %choice%==4 goto :ShowAdvanced
if %choice%==3 (
    if "!GATEWAY_STATUS!"=="Running (PID !GATEWAY_PID!)" (
        echo %YEL%Stopping gateway (PID !GATEWAY_PID!)...%RST%
        hermes gateway stop
        echo %BRC%Gateway stopped successfully.%RST%
        pause
    ) else (
        echo %CYN%Starting gateway in background...%RST%
        start "Hermes Gateway" cmd /c "hermes gateway"
        timeout /t 2 >nul
        echo %BRC%Gateway started (check %HERMES_HOME%\gateway.pid).%RST%
        pause
    )
    goto :ShowMainMenu
)
if %choice%==2 (
    echo %CYN%Opening Hermes Setup Wizard...%RST%
    hermes setup
    goto :ShowMainMenu
)
if %choice%==1 (
    echo %CYN%Launching Hermes Chat...%RST%
    hermes
    goto :ShowMainMenu
)

:: ---------------------------------------------------
:: 11. Advanced options menu
:: ---------------------------------------------------
:ShowAdvanced
cls
call :DashLine
echo %BRM%ADVANCED OPTIONS%RST%
call :DashLine
echo %CYN%--- MAINTENANCE %RST%
echo  %YEL%[1]%RST%  %WHT%Run Doctor%RST%               %DIM%-> Check environment%RST%
echo  %YEL%[2]%RST%  %WHT%View Logs%RST%                %DIM%-> Last 20 lines of gateway.log%RST%
echo  %YEL%[3]%RST%  %WHT%Edit Config%RST%              %DIM%-> Open config.yaml%RST%
echo  %YEL%[4]%RST%  %WHT%Restart Gateway%RST%          %DIM%-> Stop & start immediately%RST%
echo  %YEL%[5]%RST%  %WHT%Update Hermes%RST%            %DIM%-> Pull latest source %RST%
echo  %YEL%[6]%RST%    %BGB%Back to Main Menu%RST%
call :DashLine
echo %WHT%Select an option (1‑6):%RST%
choice /C 123456 /N /M "Your choice:"
set "adv=%ERRORLEVEL%"

if %adv%==6 goto :ShowMainMenu
if %adv%==5 (
    echo %CYN%Checking for updates...%RST%
    hermes update
    pause
    goto :ShowAdvanced
)
if %adv%==4 (
    echo %CYN%Restarting gateway...%RST%
    hermes gateway restart
    echo %BRC%Gateway restart issued.%RST%
    pause
    goto :ShowMainMenu
)
if %adv%==3 (
    echo %CYN%Opening config.yaml…%RST%
    hermes config edit
    pause
    goto :ShowAdvanced
)
if %adv%==2 (
    echo %CYN%Showing gateway log…%RST%
    if exist "%HERMES_HOME%\logs\gateway.log" (
        powershell -NoProfile -Command "Get-Content '%HERMES_HOME%\logs\gateway.log' -Tail 20"
    ) else (
        echo %YEL%[INFO]%RST% No gateway log found.
    )
    pause
    goto :ShowAdvanced
)
if %adv%==1 (
    echo %CYN%Running Hermes Doctor…%RST%
    hermes doctor
    pause
    goto :ShowAdvanced
)

:: ---------------------------------------------------
:: 12. Clean exit
:: ---------------------------------------------------
:EofExit
echo.
echo %DIM%Shutting down Hermes Launcher. Goodbye!%RST%
timeout /t 1 >nul
endlocal & exit /b 0