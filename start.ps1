# SPHEREx Sky Explorer - PowerShell Launcher
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "       SPHEREx SKY EXPLORER -- 3D CELESTIAL OBSERVATORY LAUNCHER" -ForegroundColor Cyan
Write-Host "         2026 NASA Space Apps Challenge : Planet X and SPHEREx" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = $PSScriptRoot
if (-not $rootDir) { $rootDir = Get-Location }
$backendDir = Join-Path $rootDir "backend"
$frontendDir = Join-Path $rootDir "frontend"

# 1. Check Python virtual environment
Write-Host "[*] Checking Backend Python environment..." -ForegroundColor Yellow
$pythonExe = Join-Path $backendDir "venv\Scripts\python.exe"
if (Test-Path $pythonExe) {
    Write-Host "    Found virtual environment at backend\venv" -ForegroundColor Green
} else {
    $pythonExe = "python"
    Write-Host "    Using system Python" -ForegroundColor Gray
}

# 2. Check Node.js and Frontend dependencies
Write-Host "[*] Checking Frontend Node.js environment..." -ForegroundColor Yellow
$nodeModules = Join-Path $frontendDir "node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Host "    Installing frontend npm packages..." -ForegroundColor Yellow
    Push-Location $frontendDir
    npm install
    Pop-Location
}

Write-Host ""
Write-Host "[*] Starting Services..." -ForegroundColor Yellow
Write-Host "    [1/2] Launching FastAPI Backend (Port 8000)..." -ForegroundColor Green
Start-Process cmd -ArgumentList "/k cd /d `"$backendDir`" && `"$pythonExe`" -m uvicorn main:app --host 127.0.0.1 --port 8000"

Write-Host "    [2/2] Launching Next.js 3D Frontend (Port 3000)..." -ForegroundColor Green
Start-Process cmd -ArgumentList "/k cd /d `"$frontendDir`" && npm run dev"

Write-Host ""
Write-Host "[*] Waiting for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

Write-Host "[*] Opening SPHEREx Sky Explorer in your default browser..." -ForegroundColor Cyan
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "==============================================================================" -ForegroundColor Green
Write-Host "  SUCCESS! SPHEREx Sky Explorer is running." -ForegroundColor Green
Write-Host ""
Write-Host "  - 3D Frontend:   http://localhost:3000"
Write-Host "  - 3D Explorer:   http://localhost:3000/explorer"
Write-Host "  - Backend API:   http://127.0.0.1:8000"
Write-Host "  - API Docs:      http://127.0.0.1:8000/docs"
Write-Host "  - Health Check:  http://127.0.0.1:8000/health"
Write-Host ""
Write-Host "  To shut down: Close the two opened terminal windows (Backend and Frontend)."
Write-Host "==============================================================================" -ForegroundColor Green
