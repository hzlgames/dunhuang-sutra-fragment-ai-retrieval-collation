@echo off
setlocal enabledelayedexpansion
cd /d %~dp0
title Setup Gallica MCP Server (sweet-bnf)

echo ========================================
echo   Setup Gallica MCP Server (sweet-bnf)
echo ========================================
echo.

:: Check Node.js
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found.
    echo Please install Node.js first:
    echo   https://nodejs.org/
    echo.
    echo After installing Node.js, run this script again.
    pause
    exit /b 1
)

for /f "tokens=1" %%a in ('node --version 2^>nul') do set nodever=%%a
echo [INFO] Node.js %nodever% detected

:: Check npm
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm not found. Please reinstall Node.js.
    pause
    exit /b 1
)

:: Set MCP directory
set MCP_DIR=%~dp0mcp-servers\sweet-bnf

:: Check if already installed
if exist "%MCP_DIR%\package.json" (
    echo [INFO] sweet-bnf already installed at: %MCP_DIR%
    echo.
    choice /C YN /M "Reinstall/Update"
    if errorlevel 2 goto skip_install
)

:: Create directory
echo [INFO] Creating MCP server directory...
if not exist "%~dp0mcp-servers" mkdir "%~dp0mcp-servers"

:: Check git
where git >nul 2>nul
if errorlevel 1 goto no_git

:: Clone with git
echo [INFO] Cloning sweet-bnf from GitHub...
if exist "%MCP_DIR%" rmdir /s /q "%MCP_DIR%"
git clone https://github.com/ukicar/sweet-bnf.git "%MCP_DIR%"
if errorlevel 1 goto clone_failed
goto install_deps

:no_git
echo [INFO] Git not found, downloading as ZIP...
echo [INFO] Downloading from GitHub...

:: Download using PowerShell
powershell -Command "& {Invoke-WebRequest -Uri 'https://github.com/ukicar/sweet-bnf/archive/refs/heads/main.zip' -OutFile '%TEMP%\sweet-bnf.zip'}"
if errorlevel 1 goto download_failed

echo [INFO] Extracting...
if exist "%MCP_DIR%" rmdir /s /q "%MCP_DIR%"
powershell -Command "& {Expand-Archive -Path '%TEMP%\sweet-bnf.zip' -DestinationPath '%~dp0mcp-servers' -Force}"
if errorlevel 1 goto extract_failed

:: Rename extracted folder
move "%~dp0mcp-servers\sweet-bnf-main" "%MCP_DIR%" >nul 2>nul
del "%TEMP%\sweet-bnf.zip" >nul 2>nul
goto install_deps

:install_deps
echo [INFO] Installing dependencies (npm install)...
cd /d "%MCP_DIR%"
call npm install
if errorlevel 1 (
    echo [WARNING] npm install had some issues, but continuing...
)

echo [INFO] Building TypeScript...
call npm run build
if errorlevel 1 (
    echo [WARNING] Build had some issues, but continuing...
)

:skip_install
:: Update .env file
echo.
echo [INFO] Configuring environment...

set ENV_FILE=%~dp0.env
set MCP_PATH_LINE=GALLICA_MCP_PATH=%MCP_DIR%

:: Check if .env exists
if not exist "%ENV_FILE%" (
    echo [INFO] Creating .env file...
    echo # Gallica MCP Server Path> "%ENV_FILE%"
    echo %MCP_PATH_LINE%>> "%ENV_FILE%"
    echo.>> "%ENV_FILE%"
    echo # Add your GCP configuration below:>> "%ENV_FILE%"
    echo # GOOGLE_CLOUD_PROJECT=your-project-id>> "%ENV_FILE%"
    echo # GOOGLE_APPLICATION_CREDENTIALS=service-account-key.json>> "%ENV_FILE%"
    goto done
)

:: Check if GALLICA_MCP_PATH already in .env
findstr /C:"GALLICA_MCP_PATH" "%ENV_FILE%" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Adding GALLICA_MCP_PATH to .env...
    echo.>> "%ENV_FILE%"
    echo # Gallica MCP Server Path>> "%ENV_FILE%"
    echo %MCP_PATH_LINE%>> "%ENV_FILE%"
) else (
    echo [INFO] GALLICA_MCP_PATH already configured in .env
    echo [INFO] Please verify the path is correct: %MCP_DIR%
)

:done
echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo sweet-bnf installed at: %MCP_DIR%
echo.
echo GALLICA_MCP_PATH has been added to .env
echo.
echo You can now run the server and client:
echo   1. Double-click run_server.bat
echo   2. Double-click run_client.bat
echo.
pause
exit /b 0

:clone_failed
echo [ERROR] Failed to clone repository.
echo Please check your internet connection.
pause
exit /b 1

:download_failed
echo [ERROR] Failed to download from GitHub.
echo Please check your internet connection.
pause
exit /b 1

:extract_failed
echo [ERROR] Failed to extract ZIP file.
pause
exit /b 1

