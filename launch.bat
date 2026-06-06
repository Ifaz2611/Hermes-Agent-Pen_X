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
:: 0b. Centralised error printer
:: -------------------------------------------------------------------
:MkErr
setlocal & set "msg=%~1"
endlocal & set "msg=%msg%"
echo %RED%[ERROR]%RST% %msg%
exit /b 1
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
:: 3. Silent mode?
:: -------------------------------------------------------------------
set "SILENT=0"
if "%~1"=="/silent" set "SILENT=1" & shift

:: -------------------------------------------------------------------
:: 4. First‑run runtime download
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
        2>&1 | findstr /V "^$"   // hide pure PowerShell noise
    if errorlevel 1 (
        call :MkErr "Runtime‑setup script failed (exit %ERRORLEVEL%). Abort."
    )
)

:: -------------------------------------------------------------------
:: 5. Activate the portable venv (keeps PATH tidy)
:: -------------------------------------------------------------------
call "%VENV_DIR%\Scripts\activate.bat" >nul 2>&1
if errorlevel 1 (
    call :MkErr "Failed to activate virtual environment."
)

:: -------------------------------------------------------------------
:: 6. Verify source exists
:: -------------------------------------------------------------------
if not exist "%SRC_DIR%\hermes-agent" (
    call :MkErr "Hermes source missing at %SRC_DIR%\hermes-agent. Delete %CACHE_DIR% and retry."
)

:: -------------------------------------------------------------------
:: 7. Argument forwarding (handles “hermes setup” pattern)
:: -------------------------------------------------------------------
if not "%~1"=="" (
    :: Detect leading “hermes” token and drop it
    if /I "%~1"=="hermes" (
        shift
        :collect_forward
        if "%~1"=="" goto :forward_done
        set "ARGS=!ARGS! %~1"
        shift
        goto :collect_forward
    )
    set "ARGS=%*"
    :forward_done
    if defined ARGS (
        hermes %ARGS%
        exit /b %ERRORLEVEL%
    )
)

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

:: .env sanity check (simple)
if exist "%HERMES_HOME%\.env" (
    for /f "usebackq delims=" %%L in ("%HERMES_HOME%\.env") do (
        if "%%L"=="" goto :dotenv_done
        if "%%L:~0,1%"=="#" goto :dotenv_done
        set "SETUP_STATUS=Configured"
        set "SETUP_ICON=[OK]"
        set "SETUP_COLOR=%GRN%"
        goto :dotenv_done
    )
)
:dotenv_done

:: provider & model from config.yaml (PowerShell parses YAML more reliably)
for %%F in ("%HERMES_HOME%\config.yaml") do (
    if exist "%%~F" (
        for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command ^
            "$h = Get-Content '%%~F' -Raw; $p = [System.Text.RegularExpressions.Regex]::Match($h,'provider\s*:\s*''([^'']*)'''); $m = [System.Text.RegularExpressions.Regex]::Match($h,'default\s*:\s*''([^'']*)'''); ^^^
            if ($p.Success) { $env:PROVIDER_NAME = $p.Groups[1].Value } ; ^^^
            if ($m.Success) { $env:MODEL_NAME    = $m.Groups[1].Value } ; ^
            Write-Host $env:PROVIDER_NAME $env:MODEL_NAME"`) do (
            if "!PROVIDER_NAME!"=="" set "PROVIDER_NAME=!%%~L!"
            if "!MODEL_NAME!"==""    set "MODEL_NAME=!%%~L!"
        )
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

:: hermes version (PowerShell – safer than findstr)
for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command ^
    "(Get-Content '%SRC_DIR%\hermes-agent\hermes_cli\__init__.py' -Raw) -match '__version__\s*=\s*['\"']?([^'\"']+)['\"']' | Out-Null; $Matches[1]"`) do set "HERMES_VERSION=%%L"

:: -------------------------------------------------------------------
:: 9. UI Functions (colour‑aware echo, menu, etc.)
:: -------------------------------------------------------------------
:DashLine
echo %BRC%------------------------------------------------------------%RST%

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
    goto :detected_status   :: reuse the status‑engine before showing menu again
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