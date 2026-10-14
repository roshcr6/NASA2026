@echo off
setlocal

title SPHEREx Sky Explorer - Launcher
color 0B

echo ==============================================================================
echo        SPHEREx SKY EXPLORER -- 3D CELESTIAL OBSERVATORY LAUNCHER
echo          2026 NASA Space Apps Challenge : Planet X and SPHEREx
echo ==============================================================================
echo.

set ROOT_DIR=%~dp0
set BACKEND_DIR=%ROOT_DIR%backend
set FRONTEND_DIR=%ROOT_DIR%frontend

REM 1. Check Python virtual environment
echo [*] Checking Backend Python environment...
if exist "%BACKEND_DIR%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%BACKEND_DIR%\venv\Scripts\python.exe"
    echo     Found virtual environment at backend\venv
) else (
    set "PYTHON_EXE=python"
    echo     Using system Python.
)

REM 2. Check Node.js and Frontend dependencies
echo [*] Checking Frontend Node.js environment...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [*] Installing frontend npm packages...
    cd /d "%FRONTEND_DIR%"
    call npm install
)

echo.
echo [*] Starting Services...
echo     [1/2] Launching FastAPI Backend [Port 8000]...
start "SPHEREx Backend" cmd /k "cd /d "%BACKEND_DIR%" && "%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo     [2/2] Launching Next.js 3D Frontend [Port 3000]...
start "SPHEREx Frontend" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

echo.
echo [*] Waiting for services to initialize...
ping 127.0.0.1 -n 5 >nul

echo [*] Opening SPHEREx Sky Explorer in your default browser...
start http://localhost:3000

echo.
echo ==============================================================================
echo   SUCCESS! SPHEREx Sky Explorer is running.
echo.
echo   - 3D Frontend:   http://localhost:3000
echo   - 3D Explorer:   http://localhost:3000/explorer
echo   - Backend API:   http://127.0.0.1:8000
echo   - API Docs:      http://127.0.0.1:8000/docs
echo   - Health Check:  http://127.0.0.1:8000/health
echo.
echo   To shut down: Close the two opened terminal windows [Backend and Frontend].
echo ==============================================================================
echo.
pause
