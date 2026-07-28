# OSINT Platform Architecture v2.0

The backend uses capability-based routing. Each external capability has one approved provider, and a provider failure is returned as structured status data. The orchestrator does not retry the same capability through a different vendor.

## Routing Contract

| Capability | Approved provider | Runtime adapter |
|---|---|---|
| Google dorking/search | SerpAPI | `GoogleDorkingService` |
| Exact-full-name person discovery | SerpAPI plus bounded existing profile adapters | `PersonSearchService`, `PersonSearchEnricher` |
| General public web scraping | Bright Data Web Unlocker | `BrightDataWebService` |
| Instagram profile and posts | Existing Apify Instagram Actors | `InstagramProfileService`, `InstagramPostsService` |
| X/Twitter profiles and ordinary posts | Apify Scraper One X profile/posts Actor | `TwitterApifyService` |
| X/Twitter optional replies/About and explicit search | Apify Apidojo enrichment/search Actors | `TwitterApifyService` |
| LinkedIn public profile pages | Apify LinkedIn profile Actors | `LinkedInApifyService` |
| Facebook public Page data and posts | Existing Apify Facebook Actors | `FacebookApifyService` |
| Reddit public account metadata | Reddit OAuth Data API | `RedditProfileService` |
| Reddit public posts | Existing Apify Reddit Actor | `RedditApifyService` |
| Telegram | Existing public `t.me` and optional read-only MTProto collectors | `TelegramDataService`, `TelegramMTProtoService` |
| TikTok public profile and recent videos | Configurable Apify TikTok Actor | `TikTokApifyService` |
| YouTube public channel and recent uploads | YouTube Data API v3 | `YouTubeService` |
| GitHub public profile, repositories, organizations, and contributions | GitHub REST and GraphQL APIs | `GitHubService` |
| Email discovery, finding, and verification | Hunter.io | `HunterService` |
| Phone formatting and intelligence | Twilio Lookup | `TwilioLookupService` |
| Structured extraction from explicit URLs | Firecrawl Extract API | `FirecrawlService` |

`GET /api/v1/providers/status` returns this routing map, credential-presence booleans, global/country search scope, quota ceilings, safe Telegram/Twilio modes, `automatic_fallback: false`, and configured public Actor identifiers. It does not make live provider calls and never includes credentials.

Targeted routes under `/api/v1/apify/...` remain for direct X, Reddit-post, and Facebook Actor operations. They do not redefine automatic routing. LinkedIn uses Apify in both investigations and its provider route, general explicit web scraping uses Bright Data, and Google search uses SerpAPI.

The two intentional provider splits are capability-level composition rather than retry fallback:

- X profile/post collection normally uses `APIFY_TWITTER_PROFILE_ACTOR_ID`. Only an explicit replies/About request selects `APIFY_TWITTER_ENRICHMENT_ACTOR_ID`; explicit tweet search uses `APIFY_TWITTER_TWEET_ACTOR_ID`.
- Reddit profile metadata comes from application-only OAuth at `/user/{username}/about`; Reddit post history comes from `APIFY_REDDIT_ACTOR_ID`. A combined result may be `partial` when one component succeeds and the other does not.

Relevant configuration names are:

| Capability | Required credentials | Optional endpoint, timeout, or limit settings |
|---|---|---|
| Apify social collection, including X, LinkedIn, and Reddit posts | `APIFY_API_TOKEN` | `APIFY_BASE_URL`, `APIFY_TWITTER_PROFILE_ACTOR_ID`, `APIFY_TWITTER_ENRICHMENT_ACTOR_ID`, `APIFY_TWITTER_TWEET_ACTOR_ID`, `APIFY_LINKEDIN_PROFILE_ACTOR_ID`, `APIFY_LINKEDIN_POSTS_ACTOR_ID`, `APIFY_REDDIT_ACTOR_ID` |
| Reddit profile metadata | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | `REDDIT_OAUTH_TOKEN_URL`, `REDDIT_OAUTH_BASE_URL`, `REDDIT_TIMEOUT_SECONDS`, `REDDIT_TOKEN_EXPIRY_SKEW_SECONDS` |
| YouTube channels and uploads | `YOUTUBE_API_KEY` | `YOUTUBE_API_BASE_URL`, `YOUTUBE_TIMEOUT_SECONDS`, `YOUTUBE_RECENT_VIDEO_LIMIT` |
| GitHub identity and activity | `GITHUB_TOKEN` | `GITHUB_API_BASE_URL`, `GITHUB_API_VERSION`, `GITHUB_TIMEOUT_SECONDS`, `GITHUB_REPO_LIMIT`, `GITHUB_ORGANIZATION_LIMIT` |

Credentials are read from `backend/.env` or the process environment and must not be committed.

## Investigation Flow

1. Validate the username and optional specialist inputs.
2. Build a cache key from the request, excluding `case_id` and `cache_mode`.
3. Return a fresh cache hit when `cache_mode` is `use`.
4. Reserve bounded provider-call units before paid work is scheduled.
5. Probe public profile URLs and prioritize the requested primary platform.
6. Collect at most four paid social platforms by default. Telegram retains its existing collector and does not consume a paid-provider unit. Reddit composes OAuth profile metadata with bounded Apify posts; YouTube resolves a public channel and reads one bounded uploads-playlist page.
7. Run explicitly requested specialist work: Hunter, Twilio, Bright Data web scraping, Firecrawl extraction, and GitHub when selected or discovered. GitHub reads the profile first, then concurrently requests bounded repositories, public organizations, and GraphQL contribution totals.
8. Run a global-first, requested-platform-prioritized, category-balanced SerpAPI plan of at most ten queries, subject to the remaining provider-call budget. Country bias is optional.
9. Normalize provider results, separate reachable candidates from collected profiles and corroborated identities, and assess risk only from bounded public evidence.
10. Cache the completed response unless `cache_mode` is `bypass`.

The backward-compatible `apify_social_results` field now uses `mode: "capability_routing"`. New consumers should prefer `provider_results`, which separates `social`, `specialized`, and `search` results without assuming every result came from Apify.

## Standalone Person Search Flow

`POST /api/v1/person-search` is intentionally outside the username investigation orchestrator:

1. Apply a feature-local, direct-client-IP fixed-window rate limit before endpoint work is admitted.
2. Validate and normalize a required full name plus optional location, organization, country, platform selection, and lower request ceilings.
3. Reuse a matching cache entry or identical in-flight execution internally when available; public response metadata does not reveal cache hits, entry age, shared executions, or original duration. Response time and a stable maximum-freshness bound remain explicit.
4. Require a hard concurrent-request admission slot for each new owned execution, then build a bounded exact-name query plan. No username variants are guessed from the name.
5. Require a separately quota-managed `PERSON_SEARCH_SERPAPI_KEY` by default, reserve its SerpAPI query units in a feature-local provider-call budget, and execute sequentially without cross-vendor fallback. Shared investigation/provider credentials require an explicit server-side opt-in.
6. Accept only strict known provider hosts and profile URL paths, canonicalize them, and label every result `unverified_candidate`.
7. Only when `enrich_profiles: true`, reserve and concurrently run a bounded set of lightweight profile adapters. The default is `false`, and arbitrary search-result URLs are never fetched.
8. Bound the entire enrichment phase with one deadline, including semaphore wait time. Candidates beyond the intentional enrichment cap remain discovery-only and do not cause a partial result.
9. Preserve discovery candidates if requested enrichment is missing, stale, rate-limited, or fails; return structured partial status.
10. Cache only cleanly completed and empty responses in the person-search cache. Warning, partial, and failed results remain uncached so transient provider warnings, errors, and backoff values cannot become stale. Do not write person searches to investigation history or its optional SQLite store. Cancel provider work when its final waiter disconnects; one cancelled coalesced caller never cancels work still awaited by another.

The feature has its own router, fixed-window limiter, admission gate, cache, in-flight map, schemas, query builder, normalizer, enricher, and service. It does not change `PROVIDER_ROUTING`, `SupportedPlatform`, current provider endpoints, automatic social fanout, AI analysis, local databases, or risk scoring.

## Quota Protection

The policy is configured with these environment variables:

| Variable | Default | Meaning |
|---|---:|---|
| `INVESTIGATION_CACHE_TTL_SECONDS` | `3600` | Lifetime of a completed cached result; `0` disables the cache |
| `INVESTIGATION_CACHE_MAX_ENTRIES` | `128` | Maximum in-process LRU entries |
| `INVESTIGATION_MAX_PROVIDER_CALLS` | `24` | Maximum logical paid-provider call units per investigation |
| `INVESTIGATION_MAX_DORK_QUERIES` | `10` | Maximum SerpAPI queries per investigation |
| `INVESTIGATION_MAX_SOCIAL_PLATFORMS` | `4` | Maximum paid social platforms selected per investigation |
| `INVESTIGATION_SOCIAL_RESULT_LIMIT` | `20` | Default result-item limit passed to supported social collectors |
| `INVESTIGATION_TWITTER_RESULT_LIMIT` | `5` | X profile items in an automatic investigation; replies/About remain off |
| `INVESTIGATION_HISTORY_PERSIST_ENABLED` | `false` | Opt into plaintext local SQLite investigation history |
| `INVESTIGATION_HISTORY_MAX_ENTRIES` | `128` | Maximum durable history rows when enabled |
| `PERSON_SEARCH_ENABLED` | `true` | Enable the standalone person-search route; discovery still requires its dedicated key or explicit sharing opt-in |
| `PERSON_SEARCH_SERPAPI_KEY` | unset | Separately quota-managed SerpAPI key for person discovery |
| `PERSON_SEARCH_ALLOW_SHARED_PROVIDER_CREDENTIALS` | `false` | Explicitly allow fallback to investigation SerpAPI plus optional shared platform credentials/resources |
| `PERSON_SEARCH_MAX_QUERIES` | `5` | Maximum exact-name SerpAPI queries per person search |
| `PERSON_SEARCH_MAX_PROFILES` | `20` | Maximum normalized candidates returned |
| `PERSON_SEARCH_MAX_ENRICHMENTS` | `4` | Maximum candidates considered for profile enrichment |
| `PERSON_SEARCH_MAX_PROVIDER_CALLS` | `12` | Combined person-discovery and enrichment call-unit ceiling |
| `PERSON_SEARCH_ENRICHMENT_CONCURRENCY` | `3` | Maximum profile enrichments running concurrently within one search |
| `PERSON_SEARCH_ENRICHMENT_TIMEOUT_SECONDS` | `180` | Overall deadline for the complete enrichment phase, including concurrency wait time |
| `PERSON_SEARCH_CACHE_TTL_SECONDS` | `1800` | Feature-local cache lifetime; `0` disables it |
| `PERSON_SEARCH_CACHE_MAX_ENTRIES` | `128` | Maximum process-local person-search cache entries |
| `PERSON_SEARCH_MAX_CONCURRENT_REQUESTS` | `2` | Hard admission limit for concurrently owned person-search executions |
| `PERSON_SEARCH_RATE_LIMIT_REQUESTS` | `10` | Requests accepted per direct client within one fixed window |
| `PERSON_SEARCH_RATE_LIMIT_WINDOW_SECONDS` | `60` | Person-search fixed-window duration |

Investigation requests may lower `provider_call_limit` and `dork_query_limit`; person-search requests may lower `provider_call_limit` and `query_limit`. None can raise the configured server ceilings. The call budget counts logical operations reserved by the orchestrator; it is not a count of every HTTP request or provider-side polling request.

The explicitly requested platform reserves first, followed by explicit specialist inputs, inferred social candidates, at most one configured AI risk call, and finally SerpAPI dorks. Automatic identity correlation is deterministic and never spends an external model call or budget unit. Identical concurrent requests share one in-flight execution. Successful direct-provider reads are cached; failed or pending results are not.

The cache is process-local and in-memory. It is not Redis-backed and is cleared when the API process restarts. `cache_mode` supports:

- `use`: read a matching entry and store a miss.
- `refresh`: skip cache reads and replace the matching entry after completion.
- `bypass`: neither read nor store.

Investigation history is separate from the result cache. It remains bounded in memory. Optional SQLite history survives restarts but is default-off because it stores full investigation responses in plaintext and the application itself has no authentication. Enable it only on protected loopback/private deployments with filesystem and gateway access controls.

Telegram invite previews are always isolated, redacted, and uncached. They never fan out to search, database, AI, reporting, or non-Telegram providers.
Authorized Telegram username lookup does not query third-party bots unless `TELEGRAM_OSINT_BOT_QUERIES_ENABLED=true`; that explicit mode sends the username and inspects at most five recent messages per bot dialog for a newer, exact-target response. Target-chat history is never read, and audit fields retain sends even when a lookup times out.

## Runtime Modules

- `backend/main.py`: FastAPI application assembly, CORS, health checks, and routers.
- `backend/api/endpoints/investigation.py`: investigation orchestration, cache use, and provider budget enforcement.
- `backend/api/endpoints/providers.py`: explicit capability-provider routes.
- `backend/api/endpoints/person_search_routes.py`: standalone person-search route, cache, and in-flight deduplication.
- `backend/services/person_search`: exact-name query construction, strict candidate parsing, lightweight enrichment, and orchestration.
- `backend/services/investigation_policy.py`: in-process TTL/LRU cache and call-budget primitives.
- `backend/services`: provider adapters and normalization.
- `backend/schemas`: request and response contracts.
- `backend/database`: SQL schema, ORM models, and migrations.

## Data and Trust Boundaries

- Provider adapters accept only the minimum target data needed for their capability.
- Bright Data and Firecrawl routes reject localhost, credentials in URLs, and private or reserved IP literals.
- Provider errors are bounded and normalized; secrets are not returned.
- Reddit OAuth client credentials and access tokens remain server-side. The normalized response exposes public account metadata and rate-limit state, never OAuth secrets.
- YouTube collection is limited to public channel metadata and one bounded recent-uploads page. Private videos and private subscriber information are not inferred.
- Same-username results are identity candidates, not proof. Human corroboration is required.
- Same-name person-search results always remain unverified candidates, even when a collector confirms that the public account exists.
- HTTP reachability, collector-confirmed presence, independently corroborated identity, and direct identity evidence are separate result tiers.
- AI correlation text cannot override deterministic evidence scoring. Elevated automated risk requires a substantial exact quote, a valid evidence source reference, and a narrow explicit harmful-conduct signal; otherwise the result is `unknown`.
- Only public or otherwise authorized data may be collected.

The editable Mermaid source is stored in `ARCHITECTURE_DIAGRAM.mmd`.
