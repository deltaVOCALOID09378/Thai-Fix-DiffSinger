@echo off
:: ==========================================
:: Made And Checked By DELTA SYNTH & All Code Agentic AI Engine
:: Original by DELTA SYNTH
:: Version 1.0
:: File: Start The Auto Pipeline.bat
:: Location: \DiffSinger_Training
:: Function: DiffSinger 1-Click Auto Pipeline (Train + Export)
:: ==========================================
title DELTA SYNTH - DiffSinger Auto Pipeline
color 0B

echo ========================================================
echo      DiffSinger 1-Click Pipeline (Train + Export)
echo      Made And Checked By DELTA SYNTH ^& All Code Agentic AI Engine
echo ========================================================
echo.

if exist .venv\Scripts\activate.bat (
    echo [INFO] Activating Virtual Environment...
    call .venv\Scripts\activate.bat
)

set /p EXP_NAME="[INPUT] Please enter the Experiment Name: "
if "%EXP_NAME%"=="" (
    echo [ERROR] Experiment Name not provided. Aborting operation.
    pause
    exit /b 1
)

set "CONFIG_PATH=configs\variance.yaml"
set /p CONFIG_PATH_INP="[INPUT] Enter Config File path [Press Enter to use default: %CONFIG_PATH%]: "
if not "%CONFIG_PATH_INP%"=="" set "CONFIG_PATH=%CONFIG_PATH_INP%"

:: ------------------------------------------
:: DELTA SYNTH Standard Python Path Locator
:: ------------------------------------------
set PYTHON_PATH=runtime\python.exe
if not exist "%PYTHON_PATH%" (
    set PYTHON_PATH=A:\RVC1006AMD_Intel1\runtime\python.exe
)

echo.
echo [INFO] Starting Auto Pipeline process...
echo [INFO] Using Python at: %PYTHON_PATH%
echo [INFO] Target Experiment: %EXP_NAME%
echo.

"%PYTHON_PATH%" auto_pipeline.py --config "%CONFIG_PATH%" --exp_name "%EXP_NAME%"

echo.
echo [INFO] Auto Pipeline process has concluded.
pause
exit /b 0