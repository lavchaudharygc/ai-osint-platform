# Running the Backend Locally

## Start the API

From the repository root, create and activate a virtual environment, install dependencies, then start Uvicorn:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m backend.main
```

The development server binds to `127.0.0.1:8000` by default. Open `http://127.0.0.1:8000/` for the API index, `http://127.0.0.1:8000/docs` for Swagger UI, or `http://127.0.0.1:8000/health` for a quick health check.

## Windows socket error: WinError 10013

If Windows prints `[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`, the selected host/port is blocked or reserved by Windows, Hyper-V, IIS, another service, or security software.

Try another port:

```powershell
$env:PORT = "8010"
python -m backend.main
```

Or run Uvicorn directly with an explicit loopback host and port:

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8010
```

To inspect whether port 8000 is already in use:

```powershell
netstat -ano | findstr :8000
```

To inspect excluded/reserved Windows port ranges:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```
