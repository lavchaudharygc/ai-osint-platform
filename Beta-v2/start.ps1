# PowerShell Startup Script for Beta-v2
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=====================================================================" -ForegroundColor Gold
Write-Host "   STARTING UP POLICE CYBER CELL OSINT SOC PLATFORM (Beta-v2)" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Gold

# 1. Start Backend
Write-Host "[1/2] Starting FastAPI Backend on http://127.0.0.1:8010..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$scriptDir\backend'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload"

# 2. Start Frontend
Write-Host "[2/2] Starting Frontend Web Server on http://localhost:3000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$scriptDir\frontend'; python -m http.server 3000"

Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"

Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "   BOTH SERVERS RUNNING:" -ForegroundColor Green
Write-Host "   Backend API:  http://127.0.0.1:8010" -ForegroundColor Gray
Write-Host "   Frontend UI:  http://localhost:3000" -ForegroundColor Gray
Write-Host "=====================================================================" -ForegroundColor Green
