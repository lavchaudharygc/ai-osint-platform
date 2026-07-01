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

## Testing RapidAPI FlashAPI Enrichment

1. Subscribe to the FlashAPI API in RapidAPI.
2. Open the endpoint playground and copy the generated request URL path after `https://flashapi1.p.rapidapi.com/`.
3. Set environment variables before starting the backend:

```powershell
$env:RAPIDAPI_KEY = "your-rapidapi-key"
$env:FLASHAPI_HOST = "flashapi1.p.rapidapi.com"
$env:FLASHAPI_BASE_URL = "https://flashapi1.p.rapidapi.com"
$env:FLASHAPI_ENDPOINT_PATH = "ig/info_username/"
$env:PORT = "8010"
python -m backend.main
```

4. Open `http://127.0.0.1:8010/docs` and run `POST /api/v1/investigation/username`.
5. Check the response field `platform_data.flashapi_enrichment`.

If `RAPIDAPI_KEY` is missing, the backend returns `status: not_configured` in `flashapi_enrichment` instead of failing the whole investigation.

## Testing the OSINT Training Dataset

If `final osint .json` exists at the repository root, start the backend and open:

```text
http://127.0.0.1:8010/api/v1/training/dataset/summary
```

You can also use Swagger at `http://127.0.0.1:8010/docs` and test:

- `GET /api/v1/training/dataset/summary`
- `GET /api/v1/training/dataset/examples/{example_id}`

The username investigation endpoint includes dataset guidance under `ai_correlation_result.training_context` when examples are available.

## Avoid Re-entering Environment Variables

You do not need to type the RapidAPI variables every time. Copy `.env.example` to `.env`, put your real values in `.env`, and start the backend normally:

```powershell
Copy-Item .env.example .env
notepad .env
python -m backend.main
```

The backend automatically reads `.env` through `pydantic-settings`. The `.env` file is ignored by Git so your real API keys are not committed.


## Sprint 2 Optional Keys

For AI correlation and risk assessment, add this to `.env`:

```text
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat
```

For hashtag reverse lookup, add:

```text
TWITTER_BEARER_TOKEN=your-twitter-bearer-token
```

For local internal lookups, the backend creates `osint.db` automatically unless `LOCAL_DATABASE_URL` points to another SQLite file.
