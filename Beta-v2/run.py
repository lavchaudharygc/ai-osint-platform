"""Beta-v2 Quick Startup Script (Python)
Launches both FastAPI backend (port 8010) and Frontend HTTP server (port 3000),
then opens http://localhost:3000 in your browser.
"""

import os
import sys
import time
import subprocess
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"


def main():
    print("=====================================================================")
    print("   STARTING UP POLICE CYBER CELL OSINT SOC PLATFORM (Beta-v2)")
    print("=====================================================================")

    # 1. Start FastAPI Backend Server (Port 8010)
    print("\n[1/2] Launching FastAPI Backend Server on http://127.0.0.1:8010...")
    backend_cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8010",
        "--reload"
    ]
    backend_proc = subprocess.Popen(backend_cmd, cwd=str(BACKEND_DIR))

    # 2. Start Frontend HTTP Server (Port 3000)
    print("[2/2] Launching Frontend Web Server on http://127.0.0.1:3000...")
    frontend_cmd = [
        sys.executable, "-m", "http.server", "3000",
        "--bind", "127.0.0.1"
    ]
    frontend_proc = subprocess.Popen(frontend_cmd, cwd=str(FRONTEND_DIR))

    time.sleep(2.5)

    print("\n=====================================================================")
    print("   BOTH SERVERS STARTED SUCCESSFULLY!")
    print("   Backend API:  http://127.0.0.1:8010")
    print("   Frontend UI:  http://127.0.0.1:3000")
    print("   Opening browser...")
    print("   Press Ctrl+C to terminate both servers.")
    print("=====================================================================\n")

    webbrowser.open("http://127.0.0.1:3000")

    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down Beta-v2 servers...")
        backend_proc.terminate()
        frontend_proc.terminate()
        sys.exit(0)


if __name__ == "__main__":
    main()
