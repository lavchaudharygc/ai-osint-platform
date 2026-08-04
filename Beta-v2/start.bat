@echo off
title UP Police Cyber Cell OSINT Platform (Beta-v2)
echo =====================================================================
echo    STARTING UP POLICE CYBER CELL OSINT SOC PLATFORM (Beta-v2)
echo =====================================================================

cd /d "%~dp0backend"
echo [1/2] Launching FastAPI Backend Server on http://127.0.0.1:8010...
start "Beta-v2 Backend (Port 8010)" cmd /k "python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload"

cd /d "%~dp0frontend"
echo [2/2] Launching Frontend Web Server on http://localhost:3000...
start "Beta-v2 Frontend (Port 3000)" cmd /k "python -m http.server 3000"

timeout /t 3 >nul
start http://localhost:3000

echo =====================================================================
echo    BOTH SERVERS STARTED SUCCESSFULLY!
echo    Backend API:  http://127.0.0.1:8010
echo    Frontend UI:  http://localhost:3000
echo =====================================================================
