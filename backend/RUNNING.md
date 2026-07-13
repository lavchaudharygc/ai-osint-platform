# Running the Backend Locally

## Start the API

From the repository's `backend` directory, create and activate a virtual environment, install dependencies, then start Uvicorn:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m backend.main
```

Configuration always loads from `backend/.env`, even when another launcher uses
a different working directory. `.env.example` is a copy-only template and is
never loaded at runtime. Real process environment variables, when set, take
precedence over values in `backend/.env`.

The development server binds to `127.0.0.1:8000` by default. Open `http://127.0.0.1:8000/` for the API index, `http://127.0.0.1:8000/docs` for Swagger UI, or `http://127.0.0.1:8000/health` for a quick health check.

## Running the one-click social collection

Open Swagger UI, select `POST /api/v1/investigation/username`, and send one
normal username such as:

```json
{
  "username": "example_user",
  "platform": "instagram",
  "case_id": "CASE-001",
  "correlation_depth": 2
}
```

`platform` selects the primary profile; it does not limit which collectors run.
This one click launches nine Apify Actor runs concurrently: Instagram profile
and posts, Twitter profile and search, Reddit, LinkedIn profile and posts, and
Facebook Pages and posts. The public/read-only authorized Telegram lookup also
starts concurrently.

Inspect `apify_social_results` in the response. For normal usernames its `mode`
is `automatic_all_actors`; `summary` counts completed, empty, failed, and
unconfigured Actors; `actors` contains the nine named results; and `telegram`
contains the separate Telegram result. Each Actor reports available
Actor/run/dataset provenance and any per-Actor error. A partial failure does not
discard successful collectors. A same-username result on another platform is
only a candidate and must be corroborated before identity attribution.

Be aware that a single request can create nine separate Apify charges, some
Actors require their own paid subscription, and the response can take multiple
minutes. If Apify is also the Google-dorking fallback, that stage uses additional
Apify capacity beyond the nine social runs. Keep the request open until the configured Actor timeouts finish. The
explicit `/api/v1/apify/...` endpoints are still available for targeted tests,
but each explicit call can create another paid run.

If the Telegram input is an invite URL, use `platform: "telegram"`. Invite URLs
are deliberately isolated: the backend returns `mode: "privacy_guard"`, runs
only the read-only Telegram preview, and does not send the invite hash to Apify
or any other fan-out provider.

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
