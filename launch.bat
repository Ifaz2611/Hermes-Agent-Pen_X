@echo off
:: ===========================================================================
:: Hermes Agent - Pendrive_X (Windows Launcher)
:: ===========================================================================
:: Purpose: Portable, self-contained launcher for the Hermes AI Agent.
:: Features:
::   - Automatic first-run runtime download (~600MB)
::   - Complete environment isolation (prevents host machine pollution)
::   - Interactive dashboard for managing the agent, gateway, and settings
:: Usage: Double-click this file, or run from command line with arguments.
:: ===========================================================================

:: Enable delayed variable expansion to allow updating variables inside loops/conditionals
setlocal enabledelayedexpansion

:: ---------------------------------------------------------------------------
:: 1. Path Resolution
:: ---------------------------------------------------------------------------
:: %~dp0 resolves to the drive and path of this script, ensuring portability
:: The substring removal (~0,-1) strips the trailing backslash for cleaner paths
set "PORTABLE_ROOT=%~dp0"
set "PORTABLE_ROOT=%PORTABLE_ROOT:~0,-1%"

:: Define core directory structures
set "HERMES_HOME=%PORTABLE_ROOT%\data"
set "CACHE_DIR=%PORTABLE_ROOT%\.cache"
set "RUNTIME_DIR=%CACHE_DIR%\runtimes\windows-x64"
set "SRC_DIR=%PORTABLE_ROOT%\src"

:: ---------------------------------------------------------------------------
:: 2. First-Run Setup
:: ---------------------------------------------------------------------------
:: Check if the runtime environment is already prepared via a flag file

if not exist "%RUNTIME_DIR%\ready.flag" (
    echo.
    echo ========================================================================
    echo   %BRIGHT_CYAN%HERMES Pendrive_X - First Run Setup%RESET%
    echo ========================================================================
    echo   This will download ~600MB of runtime files for Windows x64.
    echo   Please ensure you have a stable internet connection and be patient.
    echo ========================================================================
    echo.
    
    :: Execute the PowerShell setup script, bypassing execution policy restrictions

    powershell -ExecutionPolicy Bypass -File "%PORTABLE_ROOT%\scripts\setup-windows.ps1" -Root "%PORTABLE_ROOT%"
    
    :: Check if the PowerShell script failed (errorlevel 1 or higher)

    if errorlevel 1 (
        echo.
        echo %BRIGHT_RED%[ERROR]%RESET% Setup failed. Please check your internet connection and try again.
        pause
        exit /b 1
    )
)

:: ---------------------------------------------------------------------------
:: 3. Environment Isolation
:: ---------------------------------------------------------------------------
:: Force all tools to use the portable directories, preventing writes to the host OS
set "VIRTUAL_ENV=%RUNTIME_DIR%\venv"

:: Prepend portable binaries to PATH so they take precedence over system tools
set "PATH=%VIRTUAL_ENV%\Scripts;%RUNTIME_DIR%\python;%RUNTIME_DIR%\python\Scripts;%RUNTIME_DIR%\node;%RUNTIME_DIR%\uv;%RUNTIME_DIR%\bin;%PATH%"

:: Python isolation: Prevent loading user-site packages or inheriting host Python settings
set "PYTHONNOUSERSITE=1"
set "PYTHONHOME="
set "PYTHONPATH="

:: UV (Python package manager) isolation
set "UV_NO_CONFIG=1"
set "UV_PYTHON=%RUNTIME_DIR%\python\python.exe"

:: Playwright (Browser automation) isolation
set "PLAYWRIGHT_BROWSERS_PATH=%RUNTIME_DIR%\playwright"

:: Node.js / NPM isolation
set "NODE_PATH=%RUNTIME_DIR%\node\node_modules"
set "NPM_CONFIG_PREFIX=%RUNTIME_DIR%\node"

:: Redirect Windows AppData folders to the portable cache to prevent host pollution
set "APPDATA=%PORTABLE_ROOT%\.cache\windows-appdata"
set "LOCALAPPDATA=%PORTABLE_ROOT%\.cache\windows-localappdata"

:: ---------------------------------------------------------------------------
:: 4. Source Validation
:: ---------------------------------------------------------------------------
if not exist "%SRC_DIR%\hermes-agent" (
    echo.
    echo %BRIGHT_RED%[ERROR]%RESET% Hermes source code not found in "%SRC_DIR%\hermes-agent".
    echo %DIM%Please delete the .cache folder and run the launcher again to re-download.%RESET%
    pause
    exit /b 1
)

:: Change working directory to the Hermes agent source
cd /d "%SRC_DIR%\hermes-agent"

:: ---------------------------------------------------------------------------
:: 5. Argument Parsing
:: ---------------------------------------------------------------------------
:: Capture all passed arguments
set "ARGS=%*"

:: Strip "hermes" from the start of arguments if the user typed "launch.bat hermes setup"
if /I "%~1"=="hermes" (
    set "ARGS=%ARGS:~7%"
)

:: If explicit arguments were passed, run Hermes directly and skip the interactive menu
if not "%ARGS%"=="" (
    hermes %ARGS%
    exit /b
)

:: ---------------------------------------------------------------------------
:: 6. ANSI Color Setup
:: ---------------------------------------------------------------------------
:: Dynamically detect the ESC character for ANSI color codes (For James Bond 007 compatible)

for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

:: Text Colors
set "RESET=%ESC%[0m"
set "BOLD=%ESC%[1m"
set "DIM=%ESC%[2m"
set "WHITE=%ESC%[37m"
set "BRIGHT_WHITE=%ESC%[97m"
set "GRAY=%ESC%[90m"
set "CYAN=%ESC%[36m"
set "BRIGHT_CYAN=%ESC%[96m"
set "GREEN=%ESC%[32m"
set "BRIGHT_GREEN=%ESC%[92m"
set "YELLOW=%ESC%[33m"
set "BRIGHT_YELLOW=%ESC%[93m"
set "RED=%ESC%[31m"
set "BRIGHT_RED=%ESC%[91m"
set "BLUE=%ESC%[34m"
set "BRIGHT_BLUE=%ESC%[94m"
set "MAGENTA=%ESC%[35m"
set "BRIGHT_MAGENTA=%ESC%[95m"

:: Background Colors (for headers/highlights)
set "BG_CYAN=%ESC%[46m%ESC%[30m"
set "BG_DARK=%ESC%[40m%ESC%[37m"
set "BG_BLUE=%ESC%[44m%ESC%[97m"

:: ---------------------------------------------------------------------------
:: 7. Status Detection Engine
:: ---------------------------------------------------------------------------
:detect_status
:: Initialize default status variables
set "SETUP_STATUS=Not configured"
set "SETUP_ICON=[ ]"
set "SETUP_COLOR=%RED%"
set "PROVIDER_NAME="
set "MODEL_NAME="

:: Check if .env exists and contains valid key=value pairs
if exist "%HERMES_HOME%\.env" (
    findstr /R /C:"^[A-Z].*=" "%HERMES_HOME%\.env" >nul 2>&1
    if not errorlevel 1 (
        set "SETUP_STATUS=Configured"
        set "SETUP_ICON=[OK]"
        set "SETUP_COLOR=%BRIGHT_GREEN%"
    )
)

:: Parse config.yaml to extract Provider and Model names
if exist "%HERMES_HOME%\config.yaml" (
    for /f "usebackq tokens=2 delims=: " %%a in (`findstr /R /C:"^  provider:" "%HERMES_HOME%\config.yaml"`) do (
        if not defined PROVIDER_NAME set "PROVIDER_NAME=%%a"
    )
    for /f "usebackq tokens=2 delims=: " %%a in (`findstr /R /C:"^  default:" "%HERMES_HOME%\config.yaml"`) do (
        if not defined MODEL_NAME set "MODEL_NAME=%%a"
    )
)

:: Check Gateway PID file and verify if the process is actually running
set "GATEWAY_STATUS=Stopped"
set "GATEWAY_ICON=[ ]"
set "GATEWAY_COLOR=%GRAY%"
set "GATEWAY_PID="

if exist "%HERMES_HOME%\gateway.pid" (
    for /f "usebackq tokens=2 delims=:," %%a in (`findstr /R /C:"\"pid\"" "%HERMES_HOME%\gateway.pid"`) do (
        set "raw=%%a"
        set "GATEWAY_PID=!raw: =!"
    )
)

if defined GATEWAY_PID (
    tasklist /FI "PID eq !GATEWAY_PID!" 2>nul | findstr /I "!GATEWAY_PID!" >nul
    if not errorlevel 1 (
        set "GATEWAY_STATUS=Running (PID !GATEWAY_PID!)"
        set "GATEWAY_ICON=[OK]"
        set "GATEWAY_COLOR=%BRIGHT_GREEN%"
    ) else (
        set "GATEWAY_STATUS=Stopped (stale lock)"
        set "GATEWAY_ICON=[!]"
        set "GATEWAY_COLOR=%YELLOW%"
    )
)

:: Extract Hermes version from the Python package init file
set "HERMES_VERSION=unknown"
if exist "%SRC_DIR%\hermes-agent\hermes_cli\__init__.py" (
    for /f "usebackq tokens=3" %%a in (`findstr /R /C:"__version__" "%SRC_DIR%\hermes-agent\hermes_cli\__init__.py"`) do (
        set "rawver=%%a"
        set "HERMES_VERSION=!rawver:"=!"
    )
)

:: ---------------------------------------------------------------------------
:: 8. Main Interactive Menu
:: ---------------------------------------------------------------------------
:show_menu
cls
echo.
echo %BG_BLUE%                                                                        %RESET%
echo %BG_BLUE%  %BOLD%%BRIGHT_WHITE%HERMES AGENT - PENDRIVE_X%RESET% %DIM%v!HERMES_VERSION!%RESET%                                       %BG_BLUE%  %RESET%
echo %BG_BLUE%  %DIM%Portable, Isolated AI Agent Environment%RESET%                                  %BG_BLUE%  %RESET%
echo %BG_BLUE%                                                                        %RESET%
echo.
echo %BRIGHT_CYAN%--- SYSTEM STATUS -------------------------------------------------------%RESET%
echo  %DIM%Setup    %RESET% !SETUP_COLOR!!SETUP_ICON!%RESET% %WHITE%!SETUP_STATUS!%RESET%
if defined PROVIDER_NAME echo  %DIM%Provider  %RESET% %CYAN%!PROVIDER_NAME!%RESET%
if defined MODEL_NAME echo  %DIM%Model     %RESET% %WHITE%!MODEL_NAME!%RESET%
echo  %DIM%Gateway  %RESET% !GATEWAY_COLOR!!GATEWAY_ICON!%RESET% %WHITE%!GATEWAY_STATUS!%RESET%
echo.
echo %BRIGHT_CYAN%--- MAIN ACTIONS -------------------------------------------------------%RESET%
echo  %BRIGHT_YELLOW%[1]%RESET%  %BRIGHT_WHITE%Start Hermes Chat%RESET%        %DIM%-> Launch interactive CLI%RESET%
echo  %BRIGHT_YELLOW%[2]%RESET%  %BRIGHT_WHITE%Setup / Reconfigure%RESET%      %DIM%-> Configure provider and model%RESET%

if "!GATEWAY_STATUS!"=="Running (PID !GATEWAY_PID!)" (
    echo  %BRIGHT_YELLOW%[3]%RESET%  %BRIGHT_WHITE%Stop Gateway%RESET%           %DIM%-> %RED%[Currently Live]%RESET%
) else (
    echo  %BRIGHT_YELLOW%[3]%RESET%  %BRIGHT_WHITE%Start Gateway%RESET%          %DIM%-> Run API server in background%RESET%
)

echo  %BRIGHT_YELLOW%[4]%RESET%  %BRIGHT_WHITE%Advanced Options%RESET%       %DIM%-> Doctor, Logs, Config, Update%RESET%
echo  %BRIGHT_YELLOW%5%RESET%   %GRAY%Exit Launcher%RESET%            %DIM%-> Close this window%RESET%
echo %BRIGHT_CYAN%------------------------------------------------------------------------%RESET%
echo.

:: Prompt user for input using the built-in CHOICE command
echo %BRIGHT_WHITE%Select an option (1-5):%RESET% 
choice /C 12345 /N
if errorlevel 5 goto :menu_exit
if errorlevel 4 goto :show_advanced
if errorlevel 3 goto :menu_gateway
if errorlevel 2 goto :menu_setup
if errorlevel 1 goto :menu_chat
goto :show_menu

:: ---------------------------------------------------------------------------
:: 9. Menu Action Handlers
:: ---------------------------------------------------------------------------
:menu_chat
echo.
echo %BRIGHT_CYAN%Launching Hermes Chat...%RESET%
hermes
goto :show_menu

:menu_setup
echo.
echo %BRIGHT_CYAN%Opening Hermes Setup Wizard...%RESET%
hermes setup
goto :detect_status

:menu_gateway
if "!GATEWAY_STATUS!"=="Running (PID !GATEWAY_PID!)" (
    echo.
    echo %YELLOW%Stopping gateway (PID !GATEWAY_PID!)...%RESET%
    hermes gateway stop
    echo %BRIGHT_GREEN%Gateway stopped successfully.%RESET%
) else (
    echo.
    echo %BRIGHT_CYAN%Starting gateway in background...%RESET%
    start "Hermes Gateway" hermes gateway
    timeout /t 2 /nobreak >nul
    echo %BRIGHT_GREEN%Gateway startup initiated.%RESET%
)
pause
goto :detect_status

:menu_exit
echo.
echo %DIM%%GRAY%Shutting down Hermes Launcher. Goodbye!%RESET%
echo.
timeout /t 1 >nul
exit /b

:: ---------------------------------------------------------------------------
:: 10. Advanced Options Menu
:: ---------------------------------------------------------------------------
:show_advanced
cls
echo.
echo %BG_BLUE%                                                                        %RESET%
echo %BG_BLUE%  %BOLD%%BRIGHT_WHITE%ADVANCED OPTIONS%RESET%                                                        %BG_BLUE%  %RESET%
echo %BG_BLUE%  %DIM%Diagnostics, Maintenance, and Configuration%RESET%                                %BG_BLUE%  %RESET%
echo %BG_BLUE%                                                                        %RESET%
echo.
echo %BRIGHT_CYAN%--- MAINTENANCE --------------------------------------------------------%RESET%
echo  %BRIGHT_YELLOW%[1]%RESET%  %BRIGHT_WHITE%Run Doctor%RESET%            %DIM%-> Check for environment issues%RESET%
echo  %BRIGHT_YELLOW%[2]%RESET%  %BRIGHT_WHITE%View Logs%RESET%             %DIM%-> Display last 20 lines of gateway.log%RESET%
echo  %BRIGHT_YELLOW%[3]%RESET%  %BRIGHT_WHITE%Edit Config%RESET%           %DIM%-> Open config.yaml in default editor%RESET%
echo  %BRIGHT_YELLOW%[4]%RESET%  %BRIGHT_WHITE%Restart Gateway%RESET%       %DIM%-> Stop and immediately start the gateway%RESET%
echo  %BRIGHT_YELLOW%[5]%RESET%  %BRIGHT_WHITE%Update Hermes%RESET%         %DIM%-> Fetch the latest agent version%RESET%
echo  %BRIGHT_YELLOW%[6]%RESET%   %GRAY%Back to Main Menu%RESET%        %DIM%-> Return to dashboard%RESET%
echo %BRIGHT_CYAN%------------------------------------------------------------------------%RESET%
echo.

echo %BRIGHT_WHITE%Select an option (1-6):%RESET% 
choice /C 123456 /N
if errorlevel 6 goto :show_menu
if errorlevel 5 goto :adv_update
if errorlevel 4 goto :adv_restart
if errorlevel 3 goto :adv_config
if errorlevel 2 goto :adv_logs
if errorlevel 1 goto :adv_doctor
goto :show_advanced

:: ---------------------------------------------------------------------------
:: 11. Advanced Action Handlers
:: ---------------------------------------------------------------------------
:adv_doctor
echo.
echo %BRIGHT_CYAN%Running Hermes Doctor diagnostics...%RESET%
hermes doctor
echo.
pause
goto :show_advanced

:adv_logs
echo.
if exist "%HERMES_HOME%\logs\gateway.log" (
    echo %BG_DARK% === GATEWAY LOG (Last 20 Lines) === %RESET%
    powershell -Command "Get-Content '%HERMES_HOME%\logs\gateway.log' -Tail 20"
    echo %BG_DARK% =================================== %RESET%
) else (
    echo %YELLOW%[INFO]%RESET% No gateway logs found at "%HERMES_HOME%\logs\gateway.log".
)
echo.
pause
goto :show_advanced

:adv_config
echo.
echo %BRIGHT_CYAN%Opening configuration file in default editor...%RESET%
hermes config edit
goto :show_advanced

:adv_restart
echo.
echo %YELLOW%Restarting gateway...%RESET%
hermes gateway restart
echo %BRIGHT_GREEN%Gateway restart command issued.%RESET%
pause
goto :detect_status

:adv_update
echo.
echo %BRIGHT_CYAN%Checking for Hermes updates...%RESET%
hermes update
echo.
pause
goto :show_advanced