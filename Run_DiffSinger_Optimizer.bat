@echo off
setlocal EnableExtensions
chcp 65001 >nul
title DELTA SYNTH - DiffSinger Suite Optimizer (Rule 10 Compliance)

cd /d "%~dp0"
set "PY_EXE=%~dp0..\runtime\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

echo ============================================================================
echo   DELTA SYNTH - DIFFSINGER SUITE OPTIMIZER (RULE 10 COMPLIANCE)
echo   Made And Checked By DELTA SYNTH ^& All Agentic AI
echo ============================================================================

if "%~1"=="" (
    echo [INFO] Drag and drop a DiffSinger voicebank folder onto this script,
    echo        or enter the target directory path below:
    set /p "TARGET_DIR=Target Voicebank Directory: "
) else (
    set "TARGET_DIR=%~1"
)

if "%TARGET_DIR%"=="" (
    echo [ERROR] No target directory specified.
    pause
    exit /b 1
)

"%PY_EXE%" "%~dp0diffsinger_suite_optimizer.py" "%TARGET_DIR%"
pause
endlocal
