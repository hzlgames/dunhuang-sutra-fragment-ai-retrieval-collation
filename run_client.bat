@echo off
setlocal enabledelayedexpansion
cd /d %~dp0
title Dunhuang Fragment Analyzer - Desktop Client

echo ========================================
echo   Dunhuang Fragment Analyzer - Client
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 goto no_python

if not exist ".venv" goto missing_venv

echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing desktop client dependency PySide6...
    pip install "PySide6>=6.5.0" -q
)

echo [INFO] Starting desktop client...
echo [NOTE] Make sure backend server is running - run_server.bat
echo.
python -m desktop_client.app
goto end

:no_python
echo [ERROR] Python not found. Please install Python 3.10+
echo Download: https://www.python.org/downloads/
goto pause_and_exit

:missing_venv
echo [ERROR] Virtual environment not found. Please run run_server.bat first.

:pause_and_exit
pause
exit /b 1

:end
pause
