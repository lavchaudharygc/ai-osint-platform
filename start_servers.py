import subprocess
import time
import sys
import os

def start_servers():
    print("UP Cyber Cell AI-OSINT Platform Launcher")
    print("=" * 40)
    
    # 1. Paths configuration
    proj_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(proj_dir, "backend")
    frontend_dir = os.path.join(proj_dir, "frontend")
    venv_python = os.path.join(backend_dir, ".venv", "Scripts", "python.exe")
    
    if not os.path.exists(venv_python):
        print(f"Error: Virtual environment python not found at '{venv_python}'")
        print("Please configure backend virtual environment first.")
        sys.exit(1)
        
    print("Starting Backend API Server on http://127.0.0.1:8010...")
    backend_proc = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=backend_dir
    )
    
    # Give backend a moment to spin up
    time.sleep(2.5)
    
    print("Starting Frontend UI Server on http://127.0.0.1:5500...")
    frontend_proc = subprocess.Popen(
        [venv_python, "-m", "http.server", "5500", "--bind", "127.0.0.1"],
        cwd=frontend_dir
    )
    
    print("\nSystem running! Press Ctrl+C to terminate both servers.")
    print("-> Frontend: http://127.0.0.1:5500")
    print("-> Backend API: http://127.0.0.1:8010")
    print("=" * 40)
    
    try:
        while True:
            # Check if any process has exited unexpectedly
            if backend_proc.poll() is not None:
                print("Backend server stopped unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend server stopped unexpectedly.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping servers...")
    finally:
        backend_proc.terminate()
        frontend_proc.terminate()
        backend_proc.wait()
        frontend_proc.wait()
        print("Both servers successfully stopped. Goodbye!")

if __name__ == "__main__":
    start_servers()
