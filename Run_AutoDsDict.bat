@echo off
REM ==============================================================================
REM File Name: Run_AutoDsDict.bat
REM Version: 1.1
REM Target Path: DiffTrainer-main\Run_AutoDsDict.bat
REM Role: Drag-and-Drop Automated DiffSinger Dictionary Generator Launcher
REM Credits: Made And Checked By DELTA SYNTH & All Agentic AI
REM Original by agentasteriski (DiffTrainer) & Patiphat Wongyai (Delta)
REM ==============================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"
title DELTA SYNTH - AutoDsDict Generator v1.1
color 0C

set "PYTHON_EXE=%~dp0runtime\python.exe"
if not exist "%PYTHON_EXE%" (
    if exist "%~dp0..\runtime\python.exe" (
        set "PYTHON_EXE=%~dp0..\runtime\python.exe"
    ) else (
        set "PYTHON_EXE=python"
    )
)

set "SCRIPT_PATH=%~dp0dt_modules\autodsdict.py"
if not exist "%SCRIPT_PATH%" (
    set "SCRIPT_PATH=%~dp0autodsdict.py"
)

echo ==============================================================================
echo   DELTA SYNTH - AUTOMATED DIFFSINGER DICTIONARY GENERATOR (v1.1)
echo   Made And Checked By DELTA SYNTH ^& All Agentic AI
echo ==============================================================================
echo   Python Runtime : "%PYTHON_EXE%"
echo   Target Script  : "%SCRIPT_PATH%"
echo ==============================================================================

if "%~1"=="" goto :INTERACTIVE_LOOP

:DRAG_AND_DROP_LOOP
if "%~1"=="" goto :INTERACTIVE_LOOP
echo.
echo [PROCESSING] Generating dsdict.yaml for: "%~1"
"%PYTHON_EXE%" "%SCRIPT_PATH%" "%~1" "%~1"
shift
goto :DRAG_AND_DROP_LOOP

:INTERACTIVE_LOOP
echo.
echo ------------------------------------------------------------------------------
echo   Drag and drop an Acoustic Checkpoint folder here and press ENTER.
echo   Type X and press ENTER to exit.
echo ------------------------------------------------------------------------------
set "TARGET_DIR="
set /p "TARGET_DIR=Target Folder: "

if /i "%TARGET_DIR%"=="X" exit /b 0
if "%TARGET_DIR%"=="" goto :INTERACTIVE_LOOP

set "CLEAN_DIR=%TARGET_DIR:"=%"
if exist "%CLEAN_DIR%" (
    echo.
    echo [PROCESSING] Generating dsdict.yaml for: "%CLEAN_DIR%"
    "%PYTHON_EXE%" "%SCRIPT_PATH%" "%CLEAN_DIR%" "%CLEAN_DIR%"
) else (
    echo [ERROR] Folder does not exist: "%CLEAN_DIR%"
)
goto :INTERACTIVE_LOOP