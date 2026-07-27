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

The architecture uses one provider for each capability and never switches vendors automatically after a failure. “Global” means bounded, worldwide public-source discovery; it does not mean exhaustive collection or access to private content.

| Capability | Provider | Required secret |
|---|---|---|
| Google search | SerpAPI | `SERPAPI_KEY` |
| General web pages and LinkedIn | Bright Data Web Unlocker | `BRIGHTDATA_WEB_API_KEY` |
| Instagram, X/Twitter, Reddit, Facebook, TikTok | Apify | `APIFY_API_TOKEN` |
| Telegram | Public `t.me` plus optional authorized MTProto | No secret for public lookup; `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` and a local session for MTProto |
| GitHub | GitHub REST API | `GITHUB_TOKEN` |
| Email | Hunter.io | `HUNTER_API_KEY` |
| Phone | Twilio Lookup | API key pair or Account SID/Auth Token |
| Structured extraction | Firecrawl | `FIRECRAWL_API_KEY` |

Minimal `.env` example:

```env
HOST=127.0.0.1
PORT=8010

SERPAPI_KEY=
SERPAPI_COUNTRY_CODE=

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

# Optional authorized Telegram session. Third-party bot queries stay off.
TELEGRAM_MTPROTO_ENABLED=false
TELEGRAM_OSINT_BOT_QUERIES_ENABLED=false
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

The response should show `automatic_fallback` as `false`, the complete routing
map, global or country-biased search scope, active limits, and booleans
indicating which credential fields are present. This status request does not
call an external provider.

The status endpoint is not a live health check. `configured: true` does not
prove credential validity, account entitlement, available credits, quota, or
provider availability. `live_validation_performed` remains `false` until you
run an explicit capability request, which may consume provider quota.

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

The public URL probe prioritizes the requested platform and selects at most four paid social platforms by default. It no longer starts every available Actor unconditionally. Each selected capability uses only its assigned provider; skipped and budget-denied capabilities are visible in the response and counted by the social `summary.skipped` field. HTTP probe responses are unverified URL candidates; only successful collector output is collector-confirmed evidence.

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
INVESTIGATION_HISTORY_PERSIST_ENABLED=false
INVESTIGATION_HISTORY_DB_PATH=./data/investigations.sqlite3
INVESTIGATION_HISTORY_MAX_ENTRIES=128
INVESTIGATION_MAX_PROVIDER_CALLS=24
INVESTIGATION_MAX_DORK_QUERIES=10
INVESTIGATION_MAX_SOCIAL_PLATFORMS=4
INVESTIGATION_SOCIAL_RESULT_LIMIT=20
INVESTIGATION_TWITTER_RESULT_LIMIT=5
```

- Set `INVESTIGATION_CACHE_TTL_SECONDS=0` to disable caching.
- `provider_call_limit` and `dork_query_limit` may lower the server ceilings for one request.
- `cache_mode=use` reads and stores; `refresh` skips reads but stores; `bypass` does neither.
- Cache entries are process-local and disappear on restart.
- The call count is a logical orchestration budget, not a count of every provider-side HTTP request or polling request.
- Automatic identity correlation is deterministic and never calls DeepSeek or Groq. When configured, only the separate AI risk review may reserve one logical unit; without budget, risk remains evidence-constrained and no AI network call is made.

SerpAPI search reserves one budget unit per dork query. If the remaining budget is smaller than the requested search batch, the batch is reduced. A failed provider is reported; there is no Bright Data or Apify SERP fallback.

An empty `SERPAPI_COUNTRY_CODE` gives worldwide, country-unbiased search. Set a
two-letter country code only for a case that requires regional bias. Results
remain bounded by query and per-query result limits and by what Google has
indexed.

## Investigation History

Completed investigations are retained in bounded process memory by default and
disappear when the backend restarts. Optional local persistence is explicit and
default-off:

```env
INVESTIGATION_HISTORY_PERSIST_ENABLED=true
INVESTIGATION_HISTORY_DB_PATH=./data/investigations.sqlite3
INVESTIGATION_HISTORY_MAX_ENTRIES=128
```

The SQLite database stores full investigation response JSON in plaintext. Keep
it out of source control, restrict filesystem access, use an appropriate
retention policy, and use encrypted storage or an approved database before
production deployment. If persistent storage cannot initialize, the backend
continues with in-memory history and logs a warning.

## Telegram

Telegram remains on the existing public `t.me` collector with an optional read-only MTProto path. See `docs/telegram_authorized_lookup.md` for authorization setup.

Third-party Telegram bot queries are disabled by default. Enabling
`TELEGRAM_OSINT_BOT_QUERIES_ENABLED=true` sends the investigated username to
third-party bots and inspects at most five recent messages per bot dialog for a
newer response tied to that exact username; enable it only after an explicit
case-level privacy decision. Invite previews never use this path.

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

Use `GET /api/v1/providers/status` first to avoid calling an adapter whose
credentials are absent. An unconfigured adapter normally returns
`status: "not_configured"` rather than failing the whole API. Presence is not
live validation; the smoke-test requests above can consume quota.

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

For the optional external AI risk review (identity correlation remains local
and deterministic):

```env
DEEPSEEK_API_KEY=
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat

# Or use Groq when DEEPSEEK_API_KEY is empty:
GROQ_API_KEY=
GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions
GROQ_MODEL=llama-3.3-70b-versatile
```

Hashtag analysis is local-only and does not require a separate X API secret.
These integrations do not change provider routing or act as social-provider
fallbacks.

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
