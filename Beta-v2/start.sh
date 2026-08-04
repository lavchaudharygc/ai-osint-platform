#!/usr/bin/env bash
# Bash Startup Script for Beta-v2
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "====================================================================="
echo "   STARTING UP POLICE CYBER CELL OSINT SOC PLATFORM (Beta-v2)"
echo "====================================================================="

echo "[1/2] Starting FastAPI Backend on http://127.0.0.1:8010..."
(cd "$SCRIPT_DIR/backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload) &

echo "[2/2] Starting Frontend Web Server on http://localhost:3000..."
(cd "$SCRIPT_DIR/frontend" && python -m http.server 3000) &

sleep 3
echo "Servers running on http://127.0.0.1:8010 (API) and http://localhost:3000 (UI)"
