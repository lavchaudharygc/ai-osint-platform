# AI-OSINT Investigation Engine

An API and browser interface for authorized public-data investigations, cross-platform username discovery, identity-correlation support, and evidence-oriented reporting.

The current architecture is quota-aware: every external capability has one approved provider, automatic cross-provider fallback is disabled, investigations are cached, and paid-provider work is bounded per request.

## Provider Architecture

| Capability | Approved provider |
|---|---|
| Google dorking/search | SerpAPI |
| Full-name person discovery | SerpAPI plus bounded existing profile adapters |
| General public web scraping | Bright Data Web Unlocker |
| Instagram profiles and posts | Existing Apify Instagram Actors |
| X/Twitter profiles and ordinary posts | Apify Scraper One X profile/posts Actor |
| X/Twitter optional replies/About enrichment and explicit search | Apify Apidojo Actors |
| LinkedIn public profiles | Apify LinkedIn profile Actors |
| Facebook public Pages and posts | Existing Apify Facebook Actors |
| Reddit public profile metadata | Reddit OAuth Data API |
| Reddit public posts | Existing Apify Reddit Actor |
| Telegram | Existing public `t.me` and optional read-only MTProto collectors |
| TikTok public profiles and recent videos | Configurable Apify TikTok Actor |
| YouTube public channels and recent uploads | YouTube Data API v3 |
| GitHub profiles, repositories, organizations, and contributions | GitHub REST and GraphQL APIs |
| Email discovery and verification | Hunter.io |
| Phone lookup | Twilio Lookup |
| Structured extraction from explicit URLs | Firecrawl Extract API |

There is no cross-vendor provider loop. A SerpAPI failure does not call Bright Data or Apify, and a social-provider failure is returned as structured status data. The X Actor split and Reddit OAuth-plus-Apify composition are explicit capability assignments, not failure fallbacks: ordinary X profile/post collection uses Scraper One, optional X replies/About use the configured enrichment Actor, Reddit account metadata uses Reddit OAuth, and Reddit posts use Apify.

`GET /api/v1/providers/status` exposes the active routing and configuration booleans without returning credentials.

## Main Capabilities

- Public profile discovery across common social, professional, developer, and regional platforms.
- Standalone exact-full-name person search returning unverified profile, username, and photo candidates.
- Capability-routed collection with per-provider provenance and structured partial failures.
- Instagram, X/Twitter, LinkedIn, Reddit posts, Facebook, and TikTok collection through bounded Apify Actor runs.
- Reddit karma, account age, bio, and avatar collection through the Reddit OAuth Data API.
- YouTube channel metadata and bounded recent-upload collection through YouTube Data API v3.
- General public web-page retrieval through Bright Data Web Unlocker.
- Global-first SerpAPI-only Google dorking with requested-platform priority, category-balanced queries, exact-username filtering, and optional country bias.
- GitHub REST profile, repository, and public-organization enrichment plus GraphQL contribution totals.
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

# Standalone full-name person search ceilings
PERSON_SEARCH_SERPAPI_KEY=
PERSON_SEARCH_ALLOW_SHARED_PROVIDER_CREDENTIALS=false
PERSON_SEARCH_ENABLED=true
PERSON_SEARCH_MAX_QUERIES=5
PERSON_SEARCH_MAX_PROFILES=20
PERSON_SEARCH_MAX_ENRICHMENTS=4
PERSON_SEARCH_MAX_PROVIDER_CALLS=12
PERSON_SEARCH_ENRICHMENT_CONCURRENCY=3
PERSON_SEARCH_ENRICHMENT_TIMEOUT_SECONDS=180
PERSON_SEARCH_CACHE_TTL_SECONDS=1800
PERSON_SEARCH_CACHE_MAX_ENTRIES=128
PERSON_SEARCH_MAX_CONCURRENT_REQUESTS=2
PERSON_SEARCH_RATE_LIMIT_REQUESTS=10
PERSON_SEARCH_RATE_LIMIT_WINDOW_SECONDS=60

# General public web pages
BRIGHTDATA_WEB_API_KEY=
BRIGHTDATA_WEB_ZONE=web_unlocker1

# Instagram, X/Twitter, LinkedIn, Reddit posts, Facebook, and TikTok
APIFY_API_TOKEN=
APIFY_TWITTER_PROFILE_ACTOR_ID=scraper_one/x-profile-posts-scraper
APIFY_TWITTER_ENRICHMENT_ACTOR_ID=apidojo/twitter-profile-scraper
APIFY_TWITTER_TWEET_ACTOR_ID=apidojo/tweet-scraper
APIFY_LINKEDIN_PROFILE_ACTOR_ID=bebity/linkedin-premium-actor
APIFY_LINKEDIN_POSTS_ACTOR_ID=apimaestro/linkedin-posts-search-scraper-no-cookies
APIFY_TIKTOK_ACTOR_ID=clockworks/tiktok-scraper

# Reddit public account metadata (application-only OAuth)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=

# YouTube public channels and uploads
YOUTUBE_API_KEY=

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

# GitHub REST and GraphQL
GITHUB_TOKEN=
GITHUB_ORGANIZATION_LIMIT=30

# Optional durable local history (plaintext; default off)
INVESTIGATION_HISTORY_PERSIST_ENABLED=false
INVESTIGATION_HISTORY_DB_PATH=./data/investigations.sqlite3
```

The complete URLs, timeouts, Actor IDs, data-package settings, and limits are in [`backend/.env.example`](backend/.env.example).

Configuration is capability-specific: X and LinkedIn require `APIFY_API_TOKEN`; Reddit metadata requires all of `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and a descriptive `REDDIT_USER_AGENT`, while Reddit posts separately require `APIFY_API_TOKEN`; YouTube requires `YOUTUBE_API_KEY`; and all GitHub REST/GraphQL enrichments require `GITHUB_TOKEN`. Leave unrelated provider credentials empty when those capabilities are not used.

Person search uses `PERSON_SEARCH_SERPAPI_KEY` by default; use a separately quota-managed SerpAPI key so name searches cannot exhaust the investigation search allowance. `PERSON_SEARCH_ALLOW_SHARED_PROVIDER_CREDENTIALS` defaults to `false`. Setting it to `true` deliberately permits fallback to `SERPAPI_KEY` and permits explicitly requested profile enrichment to use existing platform credentials or shared network resources such as public Telegram. Enrichment is still off by default and never calls a platform whose candidate was not discovered. No additional Python package is required.

### Apify Actor Defaults

The approved Apify defaults are:

| Platform | Actor |
|---|---|
| Instagram profile | `apify/instagram-profile-scraper` |
| Instagram posts | `apify/instagram-scraper` |
| X/Twitter profile and ordinary posts | `scraper_one/x-profile-posts-scraper` |
| X/Twitter optional replies/About | `apidojo/twitter-profile-scraper` |
| X/Twitter explicit search | `apidojo/tweet-scraper` |
| Reddit | `automation-lab/reddit-scraper` |
| LinkedIn profiles | `bebity/linkedin-premium-actor` |
| LinkedIn post search | `apimaestro/linkedin-posts-search-scraper-no-cookies` |
| Facebook Pages | `apify/facebook-pages-scraper` |
| Facebook posts | `apify/facebook-posts-scraper` |
| TikTok | `clockworks/tiktok-scraper`, configurable with `APIFY_TIKTOK_ACTOR_ID` |

LinkedIn uses Apify consistently in automatic investigations and at the direct provider endpoint. Bright Data remains available for explicit general web-page scraping, not as the LinkedIn profile provider.

Automatic X profile collection requests five items from Scraper One and leaves separately billable replies/About enrichment off. The explicit X profile endpoint can opt into those features within hard caps, which selects the configured Apidojo enrichment Actor. Explicit X search uses the separate tweet-search Actor.

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

Supported primary platforms are `instagram`, `twitter`, `telegram`, `linkedin`, `reddit`, `facebook`, `tiktok`, `github`, and `youtube`.

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
| `GET /api/v1/person-search/status` | Person-search readiness and server ceilings |
| `POST /api/v1/person-search` | Exact-full-name profile, username, and photo candidate aggregation |
| `POST /api/v1/providers/web/scrape` | Bright Data public-page scrape |
| `POST /api/v1/providers/web/extract` | Firecrawl structured extraction |
| `POST /api/v1/providers/email/discover` | Hunter domain search |
| `POST /api/v1/providers/email/find` | Hunter email finder |
| `POST /api/v1/providers/email/verify` | Hunter email verification |
| `POST /api/v1/providers/phone/lookup` | Twilio Lookup |
| `POST /api/v1/providers/github/profile` | GitHub profile, repositories, organizations, and contribution totals |
| `POST /api/v1/providers/linkedin/profile` | Apify LinkedIn public profile |
| `POST /api/v1/providers/youtube/channel` | YouTube channel metadata and recent uploads |
| `POST /api/v1/providers/reddit/profile` | Reddit OAuth account metadata plus bounded Apify posts |
| `POST /api/v1/providers/tiktok/profile` | Configured Apify TikTok Actor |
| `POST /api/v1/apify/twitter/profile` | X profile/posts; optional replies/About select the enrichment Actor |
| `POST /api/v1/apify/twitter/search` | Explicit bounded X tweet search |
| `POST /api/v1/apify/reddit/collect` | Explicit Apify-only Reddit post collection |

Targeted Apify routes remain under `/api/v1/apify/...` for X, Reddit post collection, and Facebook; each call can create a separately billable Actor run. The direct LinkedIn route is Apify-backed. The direct Reddit route combines Reddit OAuth profile metadata with bounded Apify post collection; its two provider components can report partial failure independently.

## Person Search

`POST /api/v1/person-search` is separate from username investigations and does not write to investigation history. It builds exact-name SerpAPI queries, strictly accepts only recognized public profile URL shapes, and can enrich a bounded number of candidates with the lightest existing profile collector. Enrichment is an explicit opt-in: `enrich_profiles` defaults to `false`.

In the dashboard, choose **Person Search** in the left sidebar. Its form, readiness check, request state, and profile/username/photo results are isolated from the existing **OSINT Console**. The screen reads `GET /api/v1/person-search/status` when opened, shows the required environment setting when discovery is unavailable, and never submits optional enrichment unless the investigator explicitly enables it.

For quota isolation, configure `PERSON_SEARCH_SERPAPI_KEY` with a separately managed key. Existing investigation/provider credentials and shared provider resources remain unavailable to this feature unless the server operator explicitly sets `PERSON_SEARCH_ALLOW_SHARED_PROVIDER_CREDENTIALS=true`.

```json
{
  "full_name": "Ada Lovelace",
  "location": "London",
  "organization": null,
  "country_code": "GB",
  "platforms": ["linkedin", "github", "twitter", "youtube"],
  "max_profiles": 20,
  "query_limit": 5,
  "provider_call_limit": 12,
  "enrich_profiles": true,
  "max_enrichments": 4
}
```

The response contains `profiles`, platform-mapped `usernames`, collected or clearly source-labeled `photos`, counts, provider metadata, the separate provider-call budget, structured partial errors, and non-sensitive cache metadata. Every result remains `identity_status: "unverified_candidate"`; collector success confirms only that a public account was collected, not that it belongs to the named person.

When enrichment is enabled, the server applies one overall enrichment deadline. Candidates beyond the intentional `max_enrichments` cap remain discovery-only and are not treated as errors or as a reason to mark an otherwise successful search `partial`.

Person search has a feature-local, per-client-IP fixed-window request limit and a hard concurrent-execution admission limit. Excess request rate returns HTTP 429 with `Retry-After`; a new execution that cannot obtain an admission slot returns HTTP 503. Matching cache reuse and identical-request in-flight deduplication remain internal implementation details. Public cache metadata deliberately reports no hit, age, shared-in-flight state, or original execution duration, so one caller cannot learn whether or when another caller searched the same name. `searched_at` is the response-generation time; `execution_metadata.data_freshness_max_seconds` discloses the maximum cache age without revealing whether reuse occurred. Provider work is cancelled when the final waiting client disconnects, while cancellation by one coalesced caller does not cancel work still awaited by another.

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
