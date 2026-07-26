# AI-OSINT Platform API Documentation

> Deployment note: these endpoints are intended for loopback/private-network
> use. Put authentication, authorization, and rate/spend limits in front of the
> API before exposing provider routes or investigation history publicly.

Default base URL: `http://127.0.0.1:8000`

Interactive OpenAPI documentation is available at `/docs`; the schema is available at `/openapi.json`.

## API Index and Health

- `GET /` returns the API index, including the investigation and provider-routing routes.
- `GET /health` returns service status, timestamp, and API version.

## Provider Routing Contract

The backend assigns one provider to each external capability:

| Capability | Provider |
|---|---|
| Google dorking/search | SerpAPI |
| General public web scraping | Bright Data Web Unlocker |
| Instagram | Existing Apify Instagram Actors |
| X/Twitter | Existing Apify X Actors |
| LinkedIn | Bright Data Web Unlocker |
| Facebook | Existing Apify Facebook Actors |
| Reddit | Existing Apify Reddit Actor |
| Telegram | Existing public `t.me` and optional read-only MTProto collectors |
| TikTok | Configurable Apify TikTok Actor |
| GitHub | GitHub REST API |
| Email discovery and verification | Hunter.io |
| Phone lookup | Twilio Lookup |
| Structured extraction | Firecrawl Extract API |

Automatic cross-provider fallback is disabled. Missing credentials, quota failures, timeouts, and provider errors are returned by the assigned adapter; they do not cause another vendor to run.

## Provider Status

`GET /api/v1/providers/status`

Returns:

- the authoritative capability-to-provider `routing` map;
- credential/configuration booleans under `configured`;
- `automatic_fallback: false`; and
- the active `tiktok_actor_id`.

Tokens and API keys are never returned.

## Username Investigation

`POST /api/v1/investigation/username`

Supported primary platforms are `instagram`, `twitter`, `telegram`, `linkedin`, `reddit`, `facebook`, `tiktok`, and `github`.

Example:

```json
{
  "username": "example_user",
  "platform": "instagram",
  "case_id": "CASE-001",
  "correlation_depth": 2,
  "email": "person@example.com",
  "phone_number": "+14155552671",
  "company_domain": "example.com",
  "web_urls": ["https://example.com/about"],
  "extract_urls": ["https://example.com/team"],
  "extraction_prompt": "Extract public team-member names and roles.",
  "dork_query_limit": 5,
  "provider_call_limit": 16,
  "cache_mode": "use"
}
```

Only `username` is required. Optional fields trigger their assigned specialist capability:

| Field | Effect |
|---|---|
| `platform` | Prioritizes that primary profile; defaults to Instagram when omitted |
| `correlation_depth` | Controls how many public profile-probe results are exposed |
| `email` | Verifies one address with Hunter.io |
| `company_domain` | Finds an address from a collected name, or performs bounded domain discovery, with Hunter.io |
| `phone_number` | Runs Twilio Lookup |
| `web_urls` | Scrapes each explicit public URL with Bright Data |
| `extract_urls` | Runs one Firecrawl structured-extraction job for the explicit URLs |
| `extraction_prompt` | Supplies the Firecrawl extraction instruction; a safe default is used when omitted |
| `dork_query_limit` | Lowers the configured SerpAPI query ceiling; `0` skips search |
| `provider_call_limit` | Lowers the configured logical paid-provider call ceiling |
| `cache_mode` | `use`, `refresh`, or `bypass` |

### Social Selection and Cost Control

The backend first probes public profile URLs. The requested primary platform is placed first, and no more than `INVESTIGATION_MAX_SOCIAL_PLATFORMS` paid social platforms are scheduled; the default is four. A selected capability uses only its approved provider:

- Instagram: Apify profile and posts Actors.
- X/Twitter: Apify profile Actor.
- LinkedIn: Bright Data Web Unlocker.
- Reddit: Apify Reddit Actor.
- Facebook: Apify Pages and posts Actors.
- TikTok: the configured Apify TikTok Actor.
- Telegram: the existing Telegram collector, with no paid-provider budget unit.

This replaces the previous unconditional all-platform Actor fan-out. Collectors not selected by the public probe and configured limit are returned as `skipped`; budget-denied work is returned as `budget_exhausted`. One provider failure does not erase successful results. The backward-compatible social `summary` counts `total`, `completed`, `empty`, `skipped`, `failed`, and `not_configured` outcomes.

The selected platform is the primary `platform_data`. The same-username profiles in `cross_platform_matches` remain unverified identity candidates and require human corroboration.

### Search

`dorking_results` is produced exclusively by SerpAPI. There is no Bright Data or Apify search fallback. Each configured SerpAPI query reserves one logical provider-call unit. The default investigation ceiling is ten queries.

When `SERPAPI_KEY` is absent, the response is `not_configured` and includes the prepared queries. When SerpAPI fails, the response is `failed` or `completed_with_errors`, with `provider_metadata.fallback_used: false`.

### Specialist Results

Specialist outputs are returned under `provider_results.specialized`:

- `github` when GitHub is selected or found by the public profile probe;
- `contact` for Hunter and Twilio inputs;
- `web_scrapes` for Bright Data URLs; and
- `structured_extraction` for Firecrawl.

`provider_results` is the provider-neutral contract. It contains `routing`, `social`, `specialized`, and `search`. `apify_social_results` remains for backward compatibility, but its normal mode is now `capability_routing`, and it includes non-Apify LinkedIn and Telegram results alongside the Apify actor entries.

### Cache and Execution Metadata

Completed normal investigations use a process-local TTL/LRU cache. The cache key excludes `case_id` and `cache_mode`, and stores only a SHA-256 key rather than raw request input.

- `cache_mode: "use"`: read a matching entry and store a miss.
- `cache_mode: "refresh"`: skip reading and replace the matching entry after completion.
- `cache_mode: "bypass"`: neither read nor store.

On a hit, the API creates a new investigation ID and reports the source ID and age in `execution_metadata.cache`. `execution_metadata.provider_call_budget` reports `maximum`, `used`, `remaining`, `reservations`, and skipped work. The cache is cleared on process restart.

Configured DeepSeek/Groq correlation and risk calls each reserve one budget unit before SerpAPI dorks. If no unit remains, deterministic local analysis is returned. Identical concurrent investigation or direct-provider requests share one in-flight provider run. Direct provider and Apify reads use the same bounded process-local TTL cache; pending and failed responses are not cached. Investigation history is also capped by `INVESTIGATION_CACHE_MAX_ENTRIES`.

Default policy:

```env
INVESTIGATION_CACHE_TTL_SECONDS=3600
INVESTIGATION_CACHE_MAX_ENTRIES=128
INVESTIGATION_MAX_PROVIDER_CALLS=24
INVESTIGATION_MAX_DORK_QUERIES=10
INVESTIGATION_MAX_SOCIAL_PLATFORMS=4
INVESTIGATION_SOCIAL_RESULT_LIMIT=20
```

Request-level limits may lower, but never raise, the configured ceilings.

### Telegram Invite Privacy Guard

Telegram behavior remains unchanged. Public `t.me` metadata is the default, and optional authorized MTProto access is read-only.

When `platform` is `telegram` and `username` is an invite URL, the API runs only the isolated Telegram preview. The invite hash is redacted, no cache entry is read or written, and no cross-platform, search, database, AI, reporting, or non-Telegram provider receives the invite. Sending an invite URL with another platform returns HTTP 422.

## Explicit Capability Endpoints

These routes call only the provider named by the routing contract. A valid request normally returns HTTP 200 with provider-level `success`, `configured`, and `status` fields. Request validation failures return HTTP 422.

### SerpAPI Search

`POST /api/v1/providers/search/username`

```json
{
  "username": "example_user",
  "full_name": "Example User",
  "limit": 5
}
```

`limit` is clamped to `INVESTIGATION_MAX_DORK_QUERIES`.

### Bright Data Web Scrape

`POST /api/v1/providers/web/scrape`

```json
{
  "url": "https://example.com/about",
  "data_format": "markdown"
}
```

`data_format` is `markdown` or `html`. Only explicit public HTTP(S) URLs are accepted.

### Firecrawl Structured Extract

`POST /api/v1/providers/web/extract`

```json
{
  "urls": ["https://example.com/team"],
  "prompt": "Extract public names and roles.",
  "schema": {
    "type": "object",
    "properties": {
      "people": {"type": "array"}
    }
  }
}
```

At least one of `prompt` or `schema` is required. The API accepts up to five distinct public URLs and disables Firecrawl web search, subdomain expansion, and media downloads.

### Hunter.io Email Operations

- `POST /api/v1/providers/email/discover`

  ```json
  {"domain": "example.com", "limit": 10}
  ```

- `POST /api/v1/providers/email/find`

  ```json
  {"domain": "example.com", "full_name": "Example User"}
  ```

  Alternatively, supply both `first_name` and `last_name`.

- `POST /api/v1/providers/email/verify`

  ```json
  {"email": "person@example.com"}
  ```

The domain-discovery limit is bounded by `HUNTER_DOMAIN_SEARCH_LIMIT`.

### Twilio Phone Lookup

`POST /api/v1/providers/phone/lookup`

```json
{
  "phone_number": "+14155552671",
  "country_code": "US",
  "fields": ["line_type_intelligence"]
}
```

Twilio API key credentials are preferred. Account SID/Auth Token credentials are also supported. Requested data packages may have separate Twilio charges.

### GitHub REST Profile

`POST /api/v1/providers/github/profile`

```json
{
  "username": "octocat",
  "repo_limit": 10
}
```

Returns the public user profile and one bounded page of recently updated owner repositories. `repo_limit` is between 1 and 30.

### Bright Data LinkedIn Profile

`POST /api/v1/providers/linkedin/profile`

```json
{"username": "public-profile-slug"}
```

A full `https://www.linkedin.com/in/...` URL is also accepted. No Apify LinkedIn fallback is attempted.

### Apify TikTok Profile

`POST /api/v1/providers/tiktok/profile`

```json
{
  "username": "example_user",
  "max_items": 20
}
```

The Actor is set by `APIFY_TIKTOK_ACTOR_ID`; the default is `clockworks/tiktok-scraper`. Follower/following expansion, comments, and media downloads are disabled for predictable cost.

## Apify Compatibility Routes

`GET /api/v1/apify/status` reports Apify configuration and Actor IDs without exposing the token.

The following targeted compatibility routes remain available and can create separately billable Actor runs:

- `POST /api/v1/apify/twitter/profile`
- `POST /api/v1/apify/twitter/search`
- `POST /api/v1/apify/reddit/collect`
- `POST /api/v1/apify/facebook/pages`
- `POST /api/v1/apify/facebook/posts`

The legacy Apify LinkedIn routes are not registered. Use `/api/v1/providers/linkedin/profile` for the supported Bright Data LinkedIn capability.

Current social Actor defaults:

```env
APIFY_API_TOKEN=your-apify-token
APIFY_BASE_URL=https://api.apify.com/v2
APIFY_TWITTER_PROFILE_ACTOR_ID=apidojo/twitter-profile-scraper
APIFY_TWITTER_TWEET_ACTOR_ID=apidojo/tweet-scraper
APIFY_REDDIT_ACTOR_ID=automation-lab/reddit-scraper
APIFY_FACEBOOK_PAGES_ACTOR_ID=apify/facebook-pages-scraper
APIFY_FACEBOOK_POSTS_ACTOR_ID=apify/facebook-posts-scraper
APIFY_TIKTOK_ACTOR_ID=clockworks/tiktok-scraper
```

Instagram continues to use `apify/instagram-profile-scraper` and `apify/instagram-scraper`.

## Provider Environment Variables

Copy `backend/.env.example` to `backend/.env` and set only the providers you intend to use. Do not commit real keys.

```env
# Search
SERPAPI_KEY=
SERPAPI_BASE_URL=https://serpapi.com/search.json
SERPAPI_TIMEOUT_SECONDS=20
SERPAPI_RESULTS_PER_QUERY=5

# Bright Data web and LinkedIn
BRIGHTDATA_WEB_API_KEY=
BRIGHTDATA_WEB_BASE_URL=https://api.brightdata.com/request
BRIGHTDATA_WEB_ZONE=web_unlocker1
BRIGHTDATA_WEB_TIMEOUT_SECONDS=45
BRIGHTDATA_WEB_MAX_CONTENT_CHARS=500000

# Hunter.io
HUNTER_API_KEY=
HUNTER_BASE_URL=https://api.hunter.io/v2
HUNTER_TIMEOUT_SECONDS=25
HUNTER_DOMAIN_SEARCH_LIMIT=10

# Twilio Lookup
TWILIO_API_KEY=
TWILIO_API_KEY_SECRET=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_LOOKUP_BASE_URL=https://lookups.twilio.com/v2
TWILIO_LOOKUP_TIMEOUT_SECONDS=15
TWILIO_LOOKUP_FIELDS=

# Firecrawl
FIRECRAWL_API_KEY=
FIRECRAWL_BASE_URL=https://api.firecrawl.dev/v2
FIRECRAWL_HTTP_TIMEOUT_SECONDS=30
FIRECRAWL_JOB_TIMEOUT_SECONDS=120
FIRECRAWL_POLL_INTERVAL_SECONDS=2
FIRECRAWL_MAX_URLS_PER_EXTRACT=5

# GitHub
GITHUB_TOKEN=
GITHUB_API_BASE_URL=https://api.github.com
GITHUB_API_VERSION=2026-03-10
GITHUB_TIMEOUT_SECONDS=15
GITHUB_REPO_LIMIT=10
```

The legacy `BRIGHTDATA_SERP_*` and `APIFY_SERP_*` settings are not part of the supported search path. `RAPIDAPI_KEY`/FlashAPI and Instaloader are not automatic Instagram fallbacks under the capability-routing policy.

## Investigation History

- `GET /api/v1/investigation/history?limit=20&offset=0`
- `GET /api/v1/investigation/history/{investigation_id}`

History is currently process-local and in-memory. Production deployments should persist it in PostgreSQL.

## Report Generation

`POST /api/v1/reports/generate-report/{investigation_id}?format=pdf`

Supported formats are `pdf` and `html`. The investigation must exist in the current process history.

## Training Dataset

- `GET /api/v1/training/dataset/summary`
- `GET /api/v1/training/dataset/examples/{example_id}`

When the training data file is present, investigations include related guidance under `ai_correlation_result.training_context`.

## Optional AI and Local Intelligence

- DeepSeek is used for AI correlation and risk review when `DEEPSEEK_API_KEY` is configured; otherwise rules-based analysis remains available.
- Hashtag analysis is local-only and does not issue a separate X API request.
- Local SQLite/Hi-Tek lookup behavior is independent of external provider routing.

## Authorized Telegram Details

Public `t.me` scraping remains the default. Optional MTProto access can resolve public usernames and preview invite links through an existing authorized user session, subject to account privacy and membership permissions. It never joins chats, reads messages, returns phone numbers, or enumerates contacts. See `docs/telegram_authorized_lookup.md`.
