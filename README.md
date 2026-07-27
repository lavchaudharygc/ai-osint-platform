# AI-OSINT Investigation Engine

An API and browser interface for authorized public-data investigations, cross-platform username discovery, identity-correlation support, and evidence-oriented reporting.

The current architecture is quota-aware: every external capability has one approved provider, automatic cross-provider fallback is disabled, investigations are cached, and paid-provider work is bounded per request.

## Provider Architecture

| Capability | Approved provider |
|---|---|
| Google dorking/search | SerpAPI |
| General public web scraping | Bright Data Web Unlocker |
| Instagram profiles and posts | Existing Apify Instagram Actors |
| X/Twitter profiles | Existing Apify X Actor |
| LinkedIn public profiles | Bright Data Web Unlocker |
| Facebook public Pages and posts | Existing Apify Facebook Actors |
| Reddit public data | Existing Apify Reddit Actor |
| Telegram | Existing public `t.me` and optional read-only MTProto collectors |
| TikTok public profiles and recent videos | Configurable Apify TikTok Actor |
| GitHub profiles and repositories | GitHub REST API |
| Email discovery and verification | Hunter.io |
| Phone lookup | Twilio Lookup |
| Structured extraction from explicit URLs | Firecrawl Extract API |

There is no provider loop. A SerpAPI failure does not call Bright Data or Apify; a Bright Data LinkedIn failure does not call an Apify LinkedIn Actor; and a social Actor failure is returned without trying another vendor.

`GET /api/v1/providers/status` exposes the active routing and configuration booleans without returning credentials.

## Main Capabilities

- Public profile discovery across common social, professional, developer, and regional platforms.
- Capability-routed collection with per-provider provenance and structured partial failures.
- Instagram, X/Twitter, Reddit, Facebook, and TikTok collection through bounded Apify Actor runs.
- LinkedIn and general web-page retrieval through Bright Data Web Unlocker.
- Global-first SerpAPI-only Google dorking with requested-platform priority, category-balanced queries, exact-username filtering, and optional country bias.
- GitHub REST profile and repository enrichment.
- Hunter.io email discovery, finding, and verification.
- Twilio phone formatting, validation, and optional intelligence packages.
- Firecrawl structured extraction from small explicit URL sets.
- Existing safe Telegram public lookup and optional authorized read-only MTProto preview.
- Cross-platform correlation assistance, hashtag analysis, local database matching, risk review, and investigation reports.
- Process-local TTL/LRU caching, concurrent-request deduplication, bounded in-memory history, optional local SQLite history, and a per-investigation provider-call budget (including at most one configured AI risk call; identity correlation is deterministic).

Same usernames on different platforms are evidence candidates, not proof that accounts belong to the same person. Corroborate with independent public evidence and human review.

## Quota Protection

Default policy:

```env
INVESTIGATION_CACHE_TTL_SECONDS=3600
INVESTIGATION_CACHE_MAX_ENTRIES=128
INVESTIGATION_MAX_PROVIDER_CALLS=24
INVESTIGATION_MAX_DORK_QUERIES=10
INVESTIGATION_MAX_SOCIAL_PLATFORMS=4
INVESTIGATION_SOCIAL_RESULT_LIMIT=20
INVESTIGATION_TWITTER_RESULT_LIMIT=5
INVESTIGATION_HISTORY_PERSIST_ENABLED=false
INVESTIGATION_HISTORY_MAX_ENTRIES=128
```

The normal investigation flow prioritizes the requested platform, uses public profile probes to select candidates, and schedules at most four paid social platforms by default. It does not launch an unconditional all-platform Actor fan-out.

Request fields can lower the server ceilings:

- `provider_call_limit`: lower logical paid-provider budget.
- `dork_query_limit`: lower SerpAPI query count; `0` skips search.
- `cache_mode`: `use`, `refresh`, or `bypass`.

The result cache is in-process and is cleared when the backend restarts. Durable history is a separate, default-off SQLite option because it stores investigation responses locally in plaintext. Enable it only on a protected loopback/private deployment. Telegram invite previews are always isolated and uncached.

“Global” means worldwide public-source discovery without a default country bias. It does not mean exhaustive or unbounded collection: a normal scan still honors the paid-platform, query, item, URL, cache, and provider-call ceilings above.

## Quick Start

Requirements:

- Python 3.10 or newer.
- Provider accounts only for the capabilities you plan to call.

Set up the backend:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m backend.main
```

The code default is `127.0.0.1:8000`; the supplied `.env.example` uses port `8010` to match the frontend. Open:

- API docs: `http://127.0.0.1:8010/docs`
- Provider status: `http://127.0.0.1:8010/api/v1/providers/status`
- Health check: `http://127.0.0.1:8010/health`

To start both the API and static frontend after creating `backend/.venv`:

```powershell
Set-Location ..
python start_servers.py
```

The launcher serves the frontend at `http://127.0.0.1:5500` and the API at `http://127.0.0.1:8010`.

## Provider Configuration

Copy `backend/.env.example` to `backend/.env`. Do not commit real secrets.

Core provider secrets:

```env
# SerpAPI-only search
SERPAPI_KEY=
SERPAPI_COUNTRY_CODE=

# General web pages and LinkedIn
BRIGHTDATA_WEB_API_KEY=
BRIGHTDATA_WEB_ZONE=web_unlocker1

# Instagram, X/Twitter, Reddit, Facebook, and TikTok
APIFY_API_TOKEN=
APIFY_TIKTOK_ACTOR_ID=clockworks/tiktok-scraper

# Email
HUNTER_API_KEY=

# Phone: API key pair preferred
TWILIO_API_KEY=
TWILIO_API_KEY_SECRET=
# Account SID/Auth Token are also supported for local testing
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=

# Structured extraction
FIRECRAWL_API_KEY=

# GitHub REST
GITHUB_TOKEN=

# Optional durable local history (plaintext; default off)
INVESTIGATION_HISTORY_PERSIST_ENABLED=false
INVESTIGATION_HISTORY_DB_PATH=./data/investigations.sqlite3
```

The complete URLs, timeouts, Actor IDs, data-package settings, and limits are in [`backend/.env.example`](backend/.env.example).

### Apify Actor Defaults

The approved path keeps the existing social Actors and adds a configurable TikTok Actor:

| Platform | Actor |
|---|---|
| Instagram profile | `apify/instagram-profile-scraper` |
| Instagram posts | `apify/instagram-scraper` |
| X/Twitter profile | `apidojo/twitter-profile-scraper` |
| X/Twitter explicit search | `apidojo/tweet-scraper` |
| Reddit | `automation-lab/reddit-scraper` |
| Facebook Pages | `apify/facebook-pages-scraper` |
| Facebook posts | `apify/facebook-posts-scraper` |
| TikTok | `clockworks/tiktok-scraper`, configurable with `APIFY_TIKTOK_ACTOR_ID` |

LinkedIn is not part of the automatic Apify path; it uses Bright Data.

Automatic X profile collection requests five items and leaves separately billable Replies and About queries off. The explicit X endpoint can opt into those features within hard caps.

## Run an Investigation

`POST /api/v1/investigation/username`

Minimal request:

```json
{
  "username": "target_user",
  "platform": "instagram",
  "case_id": "CASE-001",
  "correlation_depth": 2,
  "dork_query_limit": 5,
  "provider_call_limit": 12,
  "cache_mode": "use"
}
```

Supported primary platforms are `instagram`, `twitter`, `telegram`, `linkedin`, `reddit`, `facebook`, `tiktok`, and `github`.

Optional specialist inputs are explicit:

```json
{
  "username": "target_user",
  "platform": "github",
  "email": "person@example.com",
  "phone_number": "+14155552671",
  "company_domain": "example.com",
  "web_urls": ["https://example.com/about"],
  "extract_urls": ["https://example.com/team"],
  "extraction_prompt": "Extract public names and roles.",
  "dork_query_limit": 3,
  "provider_call_limit": 12,
  "cache_mode": "refresh"
}
```

The response exposes:

- `platform_data`: selected primary result.
- `cross_platform_matches`: lightweight public URL-probe candidates.
- `ai_correlation_result.candidate_platforms`: reachable URL candidates only.
- `ai_correlation_result.collector_confirmed_platforms`: profiles actually returned by assigned collectors.
- `ai_correlation_result.identity_confirmed_platforms` and `identity_corroborated_platforms`: evidence-based identity tiers; HTTP 200 and username reuse alone never enter these lists.
- `provider_results.social`: provider-neutral social results.
- `provider_results.specialized`: GitHub, Hunter, Twilio, Bright Data web, and Firecrawl outputs.
- `provider_results.search`: SerpAPI result status and metadata.
- `execution_metadata`: cache and provider-call budget state.
- `dorking_results`: normalized SerpAPI search results.
- `apify_social_results`: backward-compatible envelope with `mode: "capability_routing"`.

## Explicit Provider Routes

Use these routes when a full investigation is unnecessary:

| Method and path | Capability |
|---|---|
| `GET /api/v1/providers/status` | Routing and configuration status |
| `POST /api/v1/providers/search/username` | SerpAPI username dorking |
| `POST /api/v1/providers/web/scrape` | Bright Data public-page scrape |
| `POST /api/v1/providers/web/extract` | Firecrawl structured extraction |
| `POST /api/v1/providers/email/discover` | Hunter domain search |
| `POST /api/v1/providers/email/find` | Hunter email finder |
| `POST /api/v1/providers/email/verify` | Hunter email verification |
| `POST /api/v1/providers/phone/lookup` | Twilio Lookup |
| `POST /api/v1/providers/github/profile` | GitHub profile and repositories |
| `POST /api/v1/providers/linkedin/profile` | Bright Data LinkedIn public page |
| `POST /api/v1/providers/tiktok/profile` | Configured Apify TikTok Actor |

Targeted Apify routes remain under `/api/v1/apify/...` for X, Reddit, and Facebook; each call can create a separately billable Actor run. LinkedIn is exposed only through the approved Bright Data endpoint.

## Telegram Privacy Guard

Telegram remains on its existing collectors. Public `t.me` metadata is the default; an authorized MTProto session can optionally resolve public usernames and preview invite links in read-only mode.

Third-party Telegram OSINT-bot queries are disabled by default. Setting `TELEGRAM_OSINT_BOT_QUERIES_ENABLED=true` explicitly sends the investigated username to the built-in third-party bot list and inspects at most five recent messages per bot dialog for a newer exact-target response; attempted sends, fetched bot messages, accepted responses, and target-chat access are disclosed separately.

Invite links must be sent with `platform: "telegram"`. The backend redacts the hash, bypasses cache, runs no external fan-out, and skips cross-platform search, databases, AI, and reporting. It never joins the chat or reads messages.

See [`backend/docs/telegram_authorized_lookup.md`](backend/docs/telegram_authorized_lookup.md).

## Repository Layout

```text
public-osint/
|-- backend/
|   |-- backend/
|   |   |-- api/endpoints/       FastAPI routes
|   |   |-- services/            provider adapters and analysis services
|   |   |-- schemas/             request/response validation
|   |   `-- database/            ORM, SQL, and migrations
|   |-- docs/                     backend integration notes
|   |-- tests/                    backend test suite
|   `-- .env.example             copy-only configuration template
|-- frontend/                    static browser UI
|-- docs/                        project data and research artifacts
`-- start_servers.py             local backend/frontend launcher
```

## Tests

From `backend`:

```powershell
python -m pytest
```

Provider adapter tests use mocked HTTP transports and should not consume external API quota.

## Documentation

- [API reference](backend/API_DOCUMENTATION.md)
- [Architecture](backend/ARCHITECTURE.md)
- [Mermaid architecture diagram](backend/ARCHITECTURE_DIAGRAM.mmd)
- [Local running guide](backend/RUNNING.md)
- [SerpAPI-only dorking setup](backend/docs/google_dorking_setup.md)
- [Telegram authorized lookup](backend/docs/telegram_authorized_lookup.md)

## Responsible Use

Use this project only for lawful, authorized investigations. Collect only public or otherwise authorized data, respect platform terms and privacy controls, protect provider credentials, keep case-level audit records, and require human review before identity attribution or enforcement action.
