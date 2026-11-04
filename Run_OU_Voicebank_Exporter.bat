@echo off
REM ==============================================================================
REM File Name: Run_OU_Voicebank_Exporter.bat
REM Version: 1.1
REM Target Path: DiffTrainer-main\Run_OU_Voicebank_Exporter.bat
REM Role: Drag-and-Drop OpenUtau DiffSinger Voicebank Exporter and Thai Config Updater
REM Credits: Made And Checked By DELTA SYNTH & All Agentic AI
REM Original by agentasteriski (DiffTrainer) & Patiphat Wongyai (Delta)
REM ==============================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"
title DELTA SYNTH - OpenUtau DiffSinger Voicebank Exporter v1.1
color 0C

set "PYTHON_EXE=%~dp0runtime\python.exe"
if not exist "%PYTHON_EXE%" (
    if exist "%~dp0..\runtime\python.exe" (
        set "PYTHON_EXE=%~dp0..\runtime\python.exe"
    ) else (
        set "PYTHON_EXE=python"
    )
)

echo ==============================================================================
echo   DELTA SYNTH - OPENUTAU DIFFSINGER VOICEBANK EXPORTER (v1.1)
echo   Made And Checked By DELTA SYNTH ^& All Agentic AI
echo ==============================================================================
echo   Python Runtime : "%PYTHON_EXE%"
echo ==============================================================================

if "%~1"=="" goto :INTERACTIVE_LOOP

:DRAG_AND_DROP_LOOP
if "%~1"=="" goto :INTERACTIVE_LOOP
call :PROCESS_FOLDER "%~1"
shift
goto :DRAG_AND_DROP_LOOP

:INTERACTIVE_LOOP
echo.
echo ------------------------------------------------------------------------------
echo   Drag and drop an Acoustic/Variance Checkpoint folder here and press ENTER.
echo   Or type G to launch DiffTrainer GUI, or X to exit.
echo ------------------------------------------------------------------------------
set "TARGET_DIR="
set /p "TARGET_DIR=Target Folder or Command: "

if /i "%TARGET_DIR%"=="X" exit /b 0
if /i "%TARGET_DIR%"=="G" (
    "%PYTHON_EXE%" difftrainer.py
    goto :INTERACTIVE_LOOP
)
if "%TARGET_DIR%"=="" goto :INTERACTIVE_LOOP

set "CLEAN_DIR=%TARGET_DIR:"=%"
if exist "%CLEAN_DIR%" (
    call :PROCESS_FOLDER "%CLEAN_DIR%"
) else (
    echo [ERROR] Folder does not exist: "%CLEAN_DIR%"
)
goto :INTERACTIVE_LOOP

:PROCESS_FOLDER
set "FOLDER_PATH=%~1"
set "VOICEBANK_NAME=%~nx1"
set "EXPORT_ROOT=%~dp1OpenUtau_Export"
echo.
echo [PROCESSING] Exporting OpenUtau Voicebank "%VOICEBANK_NAME%" from "%FOLDER_PATH%"...
"%PYTHON_EXE%" -c "import sys; sys.path.insert(0, r'%~dp0'); from dt_modules.basicexport import run_OU_config; run_OU_config(r'%VOICEBANK_NAME%', r'%EXPORT_ROOT%', r'%FOLDER_PATH%', r'%FOLDER_PATH%', None, True)"
echo [DONE] Output location: "%EXPORT_ROOT%\%VOICEBANK_NAME%"
exit /b 0