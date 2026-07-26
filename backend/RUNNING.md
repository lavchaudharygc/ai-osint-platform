# Running the Backend Locally

## Start the API

From the repository's `backend` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m backend.main
```

Configuration is always loaded from `backend/.env`, even when the launcher uses another working directory. `.env.example` is a copy-only template and is never loaded directly. Process environment variables override matching values from `backend/.env`.

The code default is `127.0.0.1:8000`; the supplied `.env.example` sets port `8010`. Use the port shown in the startup log:

- API index: `http://127.0.0.1:<port>/`
- Swagger UI: `http://127.0.0.1:<port>/docs`
- Health: `http://127.0.0.1:<port>/health`
- Provider status: `http://127.0.0.1:<port>/api/v1/providers/status`

Restart the API after changing `.env`.

## Configure Capability Providers

The architecture uses one provider for each capability and never switches vendors automatically after a failure.

| Capability | Provider | Required secret |
|---|---|---|
| Google search | SerpAPI | `SERPAPI_KEY` |
| General web pages and LinkedIn | Bright Data Web Unlocker | `BRIGHTDATA_WEB_API_KEY` |
| Instagram, X/Twitter, Reddit, Facebook, TikTok | Apify | `APIFY_API_TOKEN` |
| Telegram | Existing Telegram collectors | `TELEGRAM_BOT_TOKEN` and/or authorized MTProto settings as needed |
| GitHub | GitHub REST API | `GITHUB_TOKEN` |
| Email | Hunter.io | `HUNTER_API_KEY` |
| Phone | Twilio Lookup | API key pair or Account SID/Auth Token |
| Structured extraction | Firecrawl | `FIRECRAWL_API_KEY` |

Minimal `.env` example:

```env
HOST=127.0.0.1
PORT=8010

SERPAPI_KEY=

BRIGHTDATA_WEB_API_KEY=
BRIGHTDATA_WEB_BASE_URL=https://api.brightdata.com/request
BRIGHTDATA_WEB_ZONE=web_unlocker1

APIFY_API_TOKEN=
APIFY_TIKTOK_ACTOR_ID=clockworks/tiktok-scraper

HUNTER_API_KEY=

TWILIO_API_KEY=
TWILIO_API_KEY_SECRET=
# Or, for local testing:
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=

FIRECRAWL_API_KEY=
GITHUB_TOKEN=
```

The complete set of timeouts, URLs, Actor IDs, and limits is documented in `.env.example`. Never commit `backend/.env`.

### Existing and Configurable Apify Actors

The approved automatic social path keeps the existing Actors:

- Instagram: `apify/instagram-profile-scraper` and `apify/instagram-scraper`.
- X/Twitter: `apidojo/twitter-profile-scraper`.
- Reddit: `automation-lab/reddit-scraper`.
- Facebook: `apify/facebook-pages-scraper` and `apify/facebook-posts-scraper`.
- TikTok: `APIFY_TIKTOK_ACTOR_ID`, default `clockworks/tiktok-scraper`.

The X search Actor remains available through the explicit Apify route, but the normal username investigation uses the X profile Actor. LinkedIn is routed to Bright Data, not an Apify LinkedIn Actor.

## Verify Routing Without Spending Provider Quota

Start the API, then inspect configuration state:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/v1/providers/status |
    ConvertTo-Json -Depth 8
```

The response should show `automatic_fallback` as `false`, the complete routing map, and booleans indicating which providers are configured. This status request does not call an external provider.

## Run a Bounded Investigation

In Swagger, open `POST /api/v1/investigation/username`, or use PowerShell:

```powershell
$body = @{
    username = "example_user"
    platform = "instagram"
    case_id = "CASE-001"
    correlation_depth = 2
    dork_query_limit = 5
    provider_call_limit = 12
    cache_mode = "use"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri http://127.0.0.1:8010/api/v1/investigation/username `
    -ContentType "application/json" `
    -Body $body
```

The public URL probe prioritizes the requested platform and selects at most four paid social platforms by default. It no longer starts every available Actor unconditionally. Each selected capability uses only its assigned provider; skipped and budget-denied capabilities are visible in the response and counted by the social `summary.skipped` field.

Read these response fields first:

- `provider_results.routing`: the capability map.
- `provider_results.social`: provider-neutral social results.
- `provider_results.specialized`: GitHub, contact, web, and extraction results requested for this investigation.
- `provider_results.search`: SerpAPI status and metadata.
- `execution_metadata.cache`: hit/miss details.
- `execution_metadata.provider_call_budget`: used, remaining, reservations, and skipped work.
- `apify_social_results`: backward-compatible social envelope; normal mode is `capability_routing`.

Same-username results are candidates, not identity proof. Confirm with independent public evidence.

## Trigger Specialist Capabilities

Add only the inputs needed for the investigation:

```json
{
  "username": "example_user",
  "platform": "github",
  "email": "person@example.com",
  "phone_number": "+14155552671",
  "company_domain": "example.com",
  "web_urls": ["https://example.com/about"],
  "extract_urls": ["https://example.com/team"],
  "extraction_prompt": "Extract public names and roles.",
  "provider_call_limit": 12,
  "dork_query_limit": 3,
  "cache_mode": "refresh"
}
```

Each `web_urls` entry schedules one Bright Data scrape. All `extract_urls` are sent in one bounded Firecrawl Extract job. Hunter and Twilio run only when their corresponding fields are present. GitHub runs when it is the primary platform or the public profile probe finds the username.

For a single capability, use `/api/v1/providers/...` instead of a full investigation. Available routes are listed in `API_DOCUMENTATION.md` and Swagger.

## Cache and Call Limits

Default quota-protection settings:

```env
INVESTIGATION_CACHE_TTL_SECONDS=3600
INVESTIGATION_CACHE_MAX_ENTRIES=128
INVESTIGATION_MAX_PROVIDER_CALLS=24
INVESTIGATION_MAX_DORK_QUERIES=10
INVESTIGATION_MAX_SOCIAL_PLATFORMS=4
INVESTIGATION_SOCIAL_RESULT_LIMIT=20
```

- Set `INVESTIGATION_CACHE_TTL_SECONDS=0` to disable caching.
- `provider_call_limit` and `dork_query_limit` may lower the server ceilings for one request.
- `cache_mode=use` reads and stores; `refresh` skips reads but stores; `bypass` does neither.
- Cache entries are process-local and disappear on restart.
- The call count is a logical orchestration budget, not a count of every provider-side HTTP request or polling request.
- Configured DeepSeek/Groq correlation and risk operations each use one logical unit. When the budget is exhausted, the local rules-based result is used without an AI network call.

SerpAPI search reserves one budget unit per dork query. If the remaining budget is smaller than the requested search batch, the batch is reduced. A failed provider is reported; there is no Bright Data or Apify SERP fallback.

## Telegram

Telegram remains on the existing public `t.me` collector with an optional read-only MTProto path. See `docs/telegram_authorized_lookup.md` for authorization setup.

For an invite URL, set `platform` to `telegram`. The backend runs only the isolated read-only preview, redacts the invite hash, bypasses the investigation cache, and does not send the invite to any other provider or analysis stage.

## Explicit Provider Smoke Tests

Examples below can consume provider quota.

SerpAPI:

```powershell
$body = @{ username = "example_user"; limit = 2 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8010/api/v1/providers/search/username -ContentType "application/json" -Body $body
```

Bright Data web scrape:

```powershell
$body = @{ url = "https://example.com"; data_format = "markdown" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8010/api/v1/providers/web/scrape -ContentType "application/json" -Body $body
```

GitHub:

```powershell
$body = @{ username = "octocat"; repo_limit = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8010/api/v1/providers/github/profile -ContentType "application/json" -Body $body
```

Use `GET /api/v1/providers/status` first to avoid calling an unconfigured adapter. An unconfigured adapter normally returns `status: "not_configured"` rather than failing the whole API.

## Training Dataset

If `final osint .json` is present, inspect:

- `GET /api/v1/training/dataset/summary`
- `GET /api/v1/training/dataset/examples/{example_id}`

Investigation responses include related training guidance when available.

## Deployment boundary

The API defaults to `127.0.0.1` and should remain loopback-only or behind a
trusted private-network gateway. Provider-spending routes and investigation
history do not implement user authentication in this repository. Add gateway
authentication, authorization, and per-principal rate/spend limits before
exposing the service to untrusted networks.

## Optional AI and Local Services

For DeepSeek correlation and risk analysis:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat
```

For the separate X hashtag lookup:

```env
```

These integrations do not change provider routing or act as social-provider fallbacks.

## Run Tests

From `backend`:

```powershell
python -m pytest
```

Provider tests use mocked transports and should not spend external API quota.

## Windows Socket Error: WinError 10013

If the selected port is reserved or blocked, try another loopback port:

```powershell
$env:PORT = "8020"
python -m backend.main
```

Or start Uvicorn explicitly:

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8020
```

Inspect an occupied port:

```powershell
netstat -ano | findstr :8010
```

Inspect Windows excluded port ranges:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```
