@echo off
setlocal enabledelayedexpansion

REM ==================== Configurations ====================
REM Set Unreal Engine version
set "UE_VERSION=5.5"

REM Path to local config file
set "CONFIG_FILE=%~dp0DPR_Automation.cfg"

REM Initialize configuration variables
set "UE_DIR="
set "BUILD_TYPE="
set "TESTS_ARG="
set "PROJECT_PATH="

REM Load values from config file if available
if exist "%CONFIG_FILE%" (
    for /f "tokens=1,* delims=:" %%A in (%CONFIG_FILE%) do (
        set "KEY=%%A"
        set "VAL=%%B"
        set "VAL=!VAL:~1!"  REM Trim leading space
        if /i "!KEY!"=="EnginePath" set "UE_DIR=!VAL!"
        if /i "!KEY!"=="BuildType" set "BUILD_TYPE=!VAL!"
        if /i "!KEY!"=="Tests" set "TESTS_ARG=!VAL!"
        if /i "!KEY!"=="ProjectPath" set "PROJECT_PATH=!VAL!"
    )
)

REM Set defaults if configuration options are missing
if not defined UE_DIR set "UE_DIR=C:\Program Files\Epic Games\UE_%UE_VERSION%"
if not defined BUILD_TYPE set "BUILD_TYPE=editor"
if not defined TESTS_ARG set "TESTS_ARG=SamplePerformance,SampleFunctional,SampleWorldTransition"

REM ==================== Locate RunUAT.bat ====================
:FindUAT
set "UAT=%UE_DIR%\Engine\Build\BatchFiles\RunUAT.bat"

if not exist "%UAT%" (
    echo WARNING: Unreal Engine not found at %UE_DIR%
    echo.
    echo Please select your Unreal Engine installation folder:
    for /f "delims=" %%i in ('powershell -Command "Add-Type -AssemblyName System.Windows.Forms; $fbd = New-Object Windows.Forms.FolderBrowserDialog; if ($fbd.ShowDialog() -eq [Windows.Forms.DialogResult]::OK) { Write-Output $fbd.SelectedPath }"') do (
        set "UE_DIR=%%i"
    )
    set "UAT=!UE_DIR!\Engine\Build\BatchFiles\RunUAT.bat"
    if not exist "!UAT!" (
        echo ERROR: RunUAT.bat not found in !UE_DIR!. Exiting.
        pause
        exit /b 1
    )
    REM Update only EnginePath in config, preserving other lines
    set "TMP_CONFIG=%TEMP%\DPR_Automation_tmp.cfg"
    if exist "%CONFIG_FILE%" (
        (for /f "usebackq delims=" %%l in ("%CONFIG_FILE%") do (
            echo %%l | findstr /i /b /c:"EnginePath:" >nul
            if errorlevel 1 (
                echo %%l
            ) else (
                echo EnginePath: !UE_DIR!
            )
        )) > "!TMP_CONFIG!"
        move /Y "!TMP_CONFIG!" "%CONFIG_FILE%" >nul
    ) else (
        (
            echo EnginePath: !UE_DIR!
            echo BuildType: !BUILD_TYPE!
            echo Tests: !TESTS_ARG!
        ) > "%CONFIG_FILE%"
    )
)

REM ==================== Check for Python Availability ====================
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is required but was not found in your PATH. Please install Python and try again.
    pause
    exit /b 1
)

REM ==================== Prepare Log Directory ====================
set "BASE_LOGDIR=%~dp0..\Logs"

REM Create a timestamp for log folder (format: DD-MM-YYYY_HHMM)
for /f "tokens=1-5 delims=/: " %%d in ("%date% %time%") do (
    set "TIMESTAMP=%%d-%%e-%%f_%%g%%h"
)
set "TIMESTAMP=%TIMESTAMP:.=%"
set "LOGDIR=%BASE_LOGDIR%\%TIMESTAMP%"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM ==================== Locate Project File ====================
REM Use project path from config if set, otherwise default to ..\DPR\DPR.uproject relative to EnginePath
if defined PROJECT_PATH (
    set "UPROJECT=%PROJECT_PATH%"
) else (
    set "UPROJECT=%UE_DIR%\..\DPR\DPR.uproject"
)

REM Normalize project path
for %%F in ("%UPROJECT%") do set "UPROJECT=%%~fF"

if not exist "%UPROJECT%" (
    echo ERROR: Cannot find DPR.uproject at path: "%UPROJECT%"
    echo Please make sure DPR.uproject exists at this path or specify correct ProjectPath in the config file.
    pause
    exit /b 1
)

REM ==================== Build and Cook Steps ====================
if /i "%BUILD_TYPE%"=="local" (
    echo BuildType is local - Running local cook...
    call "!UAT!" BuildCookRun -nocompileeditor -nop4 -project="%UPROJECT%" ^
        -cook -stage -archive -archivedirectory="%LOGDIR%\Cooked" -platform=Win64 -clientconfig=Development -serverconfig=Development -unattended -utf8output
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Cook process failed. Exiting.
        pause
        exit /b 1
    )
) else if /i "%BUILD_TYPE%"=="editor" (
    echo BuildType is editor - Building project modules for Development Editor...
    set "UPROJECT_NAME="
    for %%F in ("%UPROJECT%") do set "UPROJECT_NAME=%%~nF"
    set "EDITOR_TARGET=!UPROJECT_NAME!Editor"
    call "%UE_DIR%\Engine\Build\BatchFiles\Build.bat" "!EDITOR_TARGET!" Win64 Development -project="%UPROJECT%" -waitmutex -FromMsBuild
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Editor build failed. Exiting.
        pause
        exit /b 1
    )
) else (
    echo ERROR: Unsupported BuildType "%BUILD_TYPE%", please specify "editor" or "local".
    pause
    exit /b 1
)

REM ==================== Run Automated Tests ====================
echo.
echo ==== Running tests: %TESTS_ARG% (Build type: %BUILD_TYPE%) ====
call "!UAT!" RunUnreal -targetPlatform=Win64 -configuration=Development -tests="%TESTS_ARG%" -project="%UPROJECT%" -build=%BUILD_TYPE% -logdir="%LOGDIR%" > "%LOGDIR%\gauntlet.txt"

echo Tests complete. Log file: "%LOGDIR%\gauntlet.txt"

REM ==================== Extract Test Summary ====================
set "LOGSUMMARY=%LOGDIR%\gauntlet_summary.txt"

if exist "%LOGDIR%\gauntlet.txt" (
    python "%~dp0extract_summary.py" "%LOGDIR%\gauntlet.txt" "%LOGSUMMARY%"
    if exist "%LOGSUMMARY%" (
        echo Summary extracted: "%LOGSUMMARY%"
    ) else (
        echo ERROR: Could not extract summary; log not found!
    )
) else (
    echo ERROR: gauntlet.txt not found, skipping summary extraction.
)

REM ==================== Generate HTML Report ====================
set "FULL_LOG=%LOGDIR%\gauntlet.txt"
set "SUMMARY_LOG=%LOGDIR%\gauntlet_summary.txt"
set "HTML_REPORT=%LOGDIR%\gauntlet_report.html"

if exist "%SUMMARY_LOG%" (
    echo Running generate_report.py ...
    python "%~dp0generate_report.py" "%SUMMARY_LOG%" "%FULL_LOG%" "%HTML_REPORT%" 2>&1
    if exist "%HTML_REPORT%" (
        echo HTML report generated: "%HTML_REPORT%"
    ) else (
        echo ERROR: HTML report generation failed.
    )
) else (
    echo ERROR: gauntlet_summary.txt not found, skipping report.
)

REM ==================== Generate Sessions Overview ====================
echo Generating gauntlet_sessions_overview.html ...
python "%~dp0generate_sessions_overview.py"
if exist "%~dp0..\Logs\gauntlet_sessions_overview.html" (
    echo Sessions overview generated: "%~dp0..\Logs\gauntlet_sessions_overview.html"
) else (
    echo ERROR: Sessions overview generation failed.
)

endlocal