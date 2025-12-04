@echo off
setlocal enabledelayedexpansion
cd /d %~dp0
title Dunhuang Fragment Analyzer - Backend Server

echo ========================================
echo   Dunhuang Fragment Analyzer - Server
echo ========================================
echo.

where python >nul 2>nul
if errorlevel 1 goto no_python

for /f "tokens=2" %%a in ('python --version 2^>nul') do set pyver=%%a
echo [INFO] Python %pyver% detected

if not exist ".venv" (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto venv_failed
)

echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [INFO] Checking and installing dependencies...
pip install -r requirements.txt -q

if not exist ".env" (
    echo.
    echo [WARNING] .env configuration file not found!
    echo Please create .env file with the following:
    echo   - GOOGLE_CLOUD_PROJECT
    echo   - GOOGLE_APPLICATION_CREDENTIALS
    echo   - VERTEX_BATCH_BUCKET [optional, for batch processing]
    echo.
    echo Press any key to continue...
    pause >nul
)

echo.
echo [INFO] Starting backend server...
echo [INFO] Server address: http://127.0.0.1:8000
echo [INFO] Press Ctrl+C to stop
echo.

python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000
goto end

:no_python
echo [ERROR] Python not found. Please install Python 3.10+
echo Download: https://www.python.org/downloads/
goto pause_and_exit

:venv_failed
echo [ERROR] Failed to create virtual environment
goto pause_and_exit

:pause_and_exit
pause
exit /b 1

:end
pause
