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
| X/Twitter profiles and ordinary posts | Apify Scraper One X profile/posts Actor |
| X/Twitter optional replies/About and explicit search | Apify Apidojo Actors |
| LinkedIn | Apify LinkedIn profile Actors |
| Facebook | Existing Apify Facebook Actors |
| Reddit public account metadata | Reddit OAuth Data API |
| Reddit public posts | Existing Apify Reddit Actor |
| Telegram | Existing public `t.me` and optional read-only MTProto collectors |
| TikTok | Configurable Apify TikTok Actor |
| YouTube | YouTube Data API v3 |
| GitHub | GitHub REST and GraphQL APIs |
| Email discovery and verification | Hunter.io |
| Phone lookup | Twilio Lookup |
| Structured extraction | Firecrawl Extract API |

Automatic cross-vendor fallback is disabled. Missing credentials, quota failures, timeouts, and provider errors are returned by the assigned adapter; they do not cause another vendor to run. The X Actor split and Reddit OAuth-plus-Apify response are intentional capability composition: they do not run because another provider failed.

“Global” in this documentation means worldwide, country-unbiased discovery of
public sources. It does not mean exhaustive collection. Every investigation is
bounded by configured query, provider-call, platform, item, and URL limits, and
private or access-controlled content remains out of scope.

## Provider Status

`GET /api/v1/providers/status`

Returns:

- the authoritative capability-to-provider `routing` map;
- credential/configuration booleans under `configured`;
- `automatic_fallback: false`; and
- the active `search_scope`, collection `limits`, safe Telegram/Twilio readiness
  metadata, persistent-history policy, and configured public Actor identifiers.

Tokens and API keys are never returned.

This is a configuration-presence endpoint, not a live provider health check.
`configured: true` means the required local credential fields are present; it
does not prove that a credential is valid or that the account has entitlement,
credits, quota, or current provider availability. The response therefore sets
`live_validation_performed` to `false`. Use an explicit, bounded capability
request when live validation is required; that request may consume quota.

## Username Investigation

`POST /api/v1/investigation/username`

Supported primary platforms are `instagram`, `twitter`, `telegram`, `linkedin`, `reddit`, `facebook`, `tiktok`, `github`, and `youtube`.

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
- X/Twitter: Scraper One for normal profiles/posts; the Apidojo enrichment Actor is used only when replies/About are explicitly requested.
- LinkedIn: Apify LinkedIn profile collection.
- Reddit: Reddit OAuth for account metadata and Apify for bounded posts.
- Facebook: Apify Pages and posts Actors.
- TikTok: the configured Apify TikTok Actor.
- YouTube: YouTube Data API v3 channel metadata and a bounded recent-uploads page.
- Telegram: the existing Telegram collector, with no paid-provider budget unit.

This replaces the previous unconditional all-platform Actor fan-out. Collectors not selected by the public probe and configured limit are returned as `skipped`; budget-denied work is returned as `budget_exhausted`. One provider failure does not erase successful results. The backward-compatible social `summary` counts `total`, `completed`, `empty`, `skipped`, `failed`, and `not_configured` outcomes.

An HTTP profile probe is discovery only. A 200 response is an unverified URL
candidate, not proof that a real profile exists and not evidence that it belongs
to the investigated person. Collector-confirmed profiles and identity
corroboration are reported separately.

The selected platform is the primary `platform_data`. The same-username profiles in `cross_platform_matches` remain unverified identity candidates and require human corroboration.

See `../docs/methodology/correlation_rules_v2.0.md` for the current evidence
states and the required separation between identity confidence and threat risk.

### Search

`dorking_results` is produced exclusively by SerpAPI. There is no Bright Data or Apify search fallback. Each configured SerpAPI query reserves one logical provider-call unit. The default investigation ceiling is ten queries.

Search is worldwide and country-unbiased by default. Set the optional
`SERPAPI_COUNTRY_CODE` to an ISO 3166-1 alpha-2 code only when a case requires a
country bias. A bounded plan starts with an exact general username query,
prioritizes the requested platform, keeps Instagram, X/Twitter, and GitHub in
the common ten-query plan, and then rotates across categories so one category
cannot consume the whole batch.

When `SERPAPI_KEY` is absent, the response is `not_configured` and includes the prepared queries. When SerpAPI fails, the response is `failed` or `completed_with_errors`, with `provider_metadata.fallback_used: false`.

### Specialist Results

Specialist outputs are returned under `provider_results.specialized`:

- `github` when GitHub is selected or found by the public profile probe;
- `contact` for Hunter and Twilio inputs;
- `web_scrapes` for Bright Data URLs; and
- `structured_extraction` for Firecrawl.

`provider_results` is the provider-neutral contract. It contains `routing`, `social`, `specialized`, and `search`. `apify_social_results` remains for backward compatibility, but its normal mode is `capability_routing`; consumers must not assume every nested result came from Apify because Telegram, Reddit OAuth metadata, and YouTube use their assigned non-Apify APIs.

### Cache and Execution Metadata

Completed normal investigations use a process-local TTL/LRU cache. The cache key excludes `case_id` and `cache_mode`, and stores only a SHA-256 key rather than raw request input.

- `cache_mode: "use"`: read a matching entry and store a miss.
- `cache_mode: "refresh"`: skip reading and replace the matching entry after completion.
- `cache_mode: "bypass"`: neither read nor store.

On a hit, the API creates a new investigation ID and reports the source ID and age in `execution_metadata.cache`. `execution_metadata.provider_call_budget` reports `maximum`, `used`, `remaining`, `reservations`, and skipped work. The cache is cleared on process restart.

Automatic identity correlation is deterministic and never spends an external AI
call or provider-budget unit. When DeepSeek or Groq is configured, only the
separate AI risk review may reserve one logical unit before SerpAPI dorks. If no
unit remains, risk stays evidence-constrained without an AI network request.
Identical concurrent investigation or direct-provider requests share one
in-flight provider run. Direct provider and Apify reads use the same bounded
process-local TTL cache; pending and failed responses are not cached. In-memory
investigation history is capped by `INVESTIGATION_CACHE_MAX_ENTRIES`; optional
durable history uses `INVESTIGATION_HISTORY_MAX_ENTRIES`.

Investigation history is separate from the result cache. It is process-local by
default. Optional SQLite persistence is disabled by default and, when enabled,
stores full response JSON as plaintext local data subject to a separate history
retention limit.

Default policy:

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

Request-level limits may lower, but never raise, the configured ceilings.

### Telegram Invite Privacy Guard

Public `t.me` metadata is the default, and optional authorized MTProto access is
read-only for normal operation. Third-party Telegram bot queries are a separate,
explicit opt-in and are disabled by default with
`TELEGRAM_OSINT_BOT_QUERIES_ENABLED=false`.

When `platform` is `telegram` and `username` is an invite URL, the API runs only the isolated Telegram preview. The invite hash is redacted, no cache entry is read or written, and no cross-platform, search, database, AI, reporting, or non-Telegram provider receives the invite. Sending an invite URL with another platform returns HTTP 422.

Enabling third-party bot queries sends a normal investigated username to the
built-in third-party bot list. It fetches at most five recent messages per bot
dialog to identify a newer response tied to that exact username. This changes
the privacy boundary and must not be enabled implicitly. Audit fields distinguish
queries attempted/sent, bot-dialog messages fetched, accepted responses, and
target-chat history access. Invite previews never use the bot-query path.

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

### GitHub Profile and Activity

`POST /api/v1/providers/github/profile`

```json
{
  "username": "octocat",
  "repo_limit": 10,
  "organization_limit": 10
}
```

Returns the public user profile, one bounded page of recently updated owner repositories, one bounded page of publicly listed organizations, and the default one-year contribution totals. Profile, repository, and organization data use the GitHub REST API; contribution totals use GitHub GraphQL. Both `repo_limit` and `organization_limit` accept 1-30; `organization_limit` is also capped by `GITHUB_ORGANIZATION_LIMIT`. If the profile succeeds but an enrichment call fails, the top-level result is `partial` and preserves the successful sections plus structured errors. Restricted/private contribution details are not exposed.

### Apify LinkedIn Profile

`POST /api/v1/providers/linkedin/profile`

```json
{"username": "public-profile-slug"}
```

A full `https://www.linkedin.com/in/...` URL is also accepted.

The direct route and automatic investigation path both use `LinkedInApifyService`. The configured bulk-profile Actor runs first; same-provider Apify profile Actors may be attempted when that Actor yields no usable profile. Bright Data is not used as a LinkedIn profile fallback.

### YouTube Data API Channel

`POST /api/v1/providers/youtube/channel`

```json
{
  "target": "@GoogleDevelopers",
  "recent_video_limit": 5
}
```

`target` accepts a channel ID, `@handle`, supported `youtube.com` channel URL, or legacy `/user/` or `/c/` URL. The adapter resolves the channel through `channels.list` using `id`, `forHandle`, or `forUsername` for legacy `/user/` URLs, normalizes channel name, description, public subscriber count, avatar, view count, and video count, then reads the channel's uploads playlist with one bounded `playlistItems.list` request. Legacy `/c/` custom names are attempted as handles because the Data API has no custom-URL lookup parameter. `recent_video_limit` is capped at 50; `0` skips the uploads request. Hidden subscriber counts remain `null` rather than being inferred.

The response uses `not_configured` when `YOUTUBE_API_KEY` is absent, `not_found` when the channel lookup returns no item, `rate_limited` or `quota_exhausted` when YouTube reports those conditions, and `provider_error` for other failed channel requests. Rate-limit responses preserve `Retry-After` metadata for backoff. If channel metadata succeeds but uploads fail, it returns the channel with top-level status `partial` and a structured upload error.

### Reddit OAuth Profile and Apify Posts

`POST /api/v1/providers/reddit/profile`

```json
{
  "username": "spez",
  "max_posts": 20
}
```

The profile component uses Reddit application-only OAuth and `/user/{username}/about` to normalize public bio, link/comment/total karma, creation timestamp, account age, avatar, and public account flags. The post component uses the configured Apify Reddit Actor with a bounded `max_posts` value. OAuth access tokens are cached in-process until shortly before expiry and are never returned.

The two components are independent. Missing Reddit OAuth credentials produce structured `not_configured` profile metadata while the Apify post component can still report its own result, and the combined response can be `partial` when only one component succeeds. No anonymous Reddit profile scraping is used.

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

The legacy Apify LinkedIn bulk/post-search routes are not registered. Use `/api/v1/providers/linkedin/profile` for the supported Apify-backed public-profile capability.

Current social Actor defaults:

```env
APIFY_API_TOKEN=your-apify-token
APIFY_BASE_URL=https://api.apify.com/v2
APIFY_TWITTER_PROFILE_ACTOR_ID=scraper_one/x-profile-posts-scraper
APIFY_TWITTER_ENRICHMENT_ACTOR_ID=apidojo/twitter-profile-scraper
APIFY_TWITTER_TWEET_ACTOR_ID=apidojo/tweet-scraper
APIFY_REDDIT_ACTOR_ID=automation-lab/reddit-scraper
APIFY_LINKEDIN_PROFILE_ACTOR_ID=bebity/linkedin-premium-actor
APIFY_LINKEDIN_POSTS_ACTOR_ID=apimaestro/linkedin-posts-search-scraper-no-cookies
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
# Empty means worldwide/global; set a two-letter code only for case-specific bias.
SERPAPI_COUNTRY_CODE=

# Bright Data general web scraping
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
GITHUB_ORGANIZATION_LIMIT=30

# YouTube Data API v3
YOUTUBE_API_KEY=
YOUTUBE_API_BASE_URL=https://www.googleapis.com/youtube/v3
YOUTUBE_TIMEOUT_SECONDS=15
YOUTUBE_RECENT_VIDEO_LIMIT=5

# Reddit application-only OAuth profile metadata
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=
REDDIT_OAUTH_TOKEN_URL=https://www.reddit.com/api/v1/access_token
REDDIT_OAUTH_BASE_URL=https://oauth.reddit.com
REDDIT_TIMEOUT_SECONDS=15
REDDIT_TOKEN_EXPIRY_SKEW_SECONDS=30

# Optional authorized Telegram session. Third-party bot queries remain off.
TELEGRAM_MTPROTO_ENABLED=false
TELEGRAM_SESSION_PATH=./data/telegram_osint
TELEGRAM_OSINT_BOT_QUERIES_ENABLED=false

# History is in memory unless explicitly enabled. SQLite content is plaintext.
INVESTIGATION_HISTORY_PERSIST_ENABLED=false
INVESTIGATION_HISTORY_DB_PATH=./data/investigations.sqlite3
INVESTIGATION_HISTORY_MAX_ENTRIES=128
INVESTIGATION_TWITTER_RESULT_LIMIT=5
```

The legacy `BRIGHTDATA_SERP_*` and `APIFY_SERP_*` settings are not part of the supported search path. `RAPIDAPI_KEY`/FlashAPI and Instaloader are not automatic Instagram fallbacks under the capability-routing policy.

## Investigation History

- `GET /api/v1/investigation/history?limit=20&offset=0`
- `GET /api/v1/investigation/history/{investigation_id}`

History is process-local and in-memory by default. To retain completed
investigations across restarts, explicitly set:

```env
INVESTIGATION_HISTORY_PERSIST_ENABLED=true
INVESTIGATION_HISTORY_DB_PATH=./data/investigations.sqlite3
INVESTIGATION_HISTORY_MAX_ENTRIES=128
```

The SQLite store contains full investigation response JSON in plaintext. Keep
the API loopback/private, restrict filesystem access, apply an appropriate
retention policy, and use encrypted storage or an approved database before a
production deployment. Persistence failure is non-fatal: the API logs a warning
and continues with bounded in-memory history.

## Report Generation

`POST /api/v1/reports/generate-report/{investigation_id}?format=pdf`

Supported formats are `pdf` and `html`. The investigation must exist in current
in-memory history or, when persistence is enabled, in the configured SQLite
history store.

## Training Dataset

- `GET /api/v1/training/dataset/summary`
- `GET /api/v1/training/dataset/examples/{example_id}`

When the training data file is present, investigations include related guidance under `ai_correlation_result.training_context`.

## Optional AI and Local Intelligence

- Automatic identity correlation is deterministic and does not call DeepSeek or Groq.
- When configured and budgeted, DeepSeek or Groq may be used once for the separate risk review; otherwise risk remains local/evidence-constrained.
- Hashtag analysis is local-only and does not issue a separate X API request.
- Local SQLite/Hi-Tek lookup behavior is independent of external provider routing.

## Authorized Telegram Details

Public `t.me` scraping remains the default. Optional MTProto access can resolve
public usernames and preview invite links through an existing authorized user
session, subject to account privacy and membership permissions. Normal operation
never joins chats, reads target-chat history, returns phone numbers, or enumerates
contacts. Optional third-party bot queries are disabled by default because they
send a username and inspect a bounded set of bot-dialog messages for a new,
target-tied response. See `docs/telegram_authorized_lookup.md`.
