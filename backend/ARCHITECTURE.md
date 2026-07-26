# OSINT Platform Architecture v2.0

The backend uses capability-based routing. Each external capability has one approved provider, and a provider failure is returned as structured status data. The orchestrator does not retry the same capability through a different vendor.

## Routing Contract

| Capability | Approved provider | Runtime adapter |
|---|---|---|
| Google dorking/search | SerpAPI | `GoogleDorkingService` |
| General public web scraping | Bright Data Web Unlocker | `BrightDataWebService` |
| Instagram profile and posts | Existing Apify Instagram Actors | `InstagramProfileService`, `InstagramPostsService` |
| X/Twitter profile data | Existing Apify X Actor | `TwitterApifyService` |
| LinkedIn public profile pages | Bright Data Web Unlocker | `LinkedInBrightDataService` |
| Facebook public Page data and posts | Existing Apify Facebook Actors | `FacebookApifyService` |
| Reddit public data | Existing Apify Reddit Actor | `RedditApifyService` |
| Telegram | Existing public `t.me` and optional read-only MTProto collectors | `TelegramDataService`, `TelegramMTProtoService` |
| TikTok public profile and recent videos | Configurable Apify TikTok Actor | `TikTokApifyService` |
| GitHub public profile and repositories | GitHub REST API | `GitHubService` |
| Email discovery, finding, and verification | Hunter.io | `HunterService` |
| Phone formatting and intelligence | Twilio Lookup | `TwilioLookupService` |
| Structured extraction from explicit URLs | Firecrawl Extract API | `FirecrawlService` |

`GET /api/v1/providers/status` returns this routing map, provider configuration booleans, `automatic_fallback: false`, and the configured TikTok Actor ID. Credentials are never included.

Legacy targeted routes under `/api/v1/apify/...` still exist for compatibility and testing. They do not define the automatic investigation architecture. In particular, LinkedIn investigations use Bright Data, and Google search uses SerpAPI.

## Investigation Flow

1. Validate the username and optional specialist inputs.
2. Build a cache key from the request, excluding `case_id` and `cache_mode`.
3. Return a fresh cache hit when `cache_mode` is `use`.
4. Reserve bounded provider-call units before paid work is scheduled.
5. Probe public profile URLs and prioritize the requested primary platform.
6. Collect at most four paid social platforms by default. Telegram retains its existing collector and does not consume a paid-provider unit.
7. Run explicitly requested specialist work: Hunter, Twilio, Bright Data web scraping, Firecrawl extraction, and GitHub when selected or discovered.
8. Run at most ten SerpAPI dork queries by default, subject to the remaining provider-call budget.
9. Normalize provider results, correlate public evidence, assess risk, and store the response in investigation history.
10. Cache the completed response unless `cache_mode` is `bypass`.

The backward-compatible `apify_social_results` field now uses `mode: "capability_routing"`. New consumers should prefer `provider_results`, which separates `social`, `specialized`, and `search` results without assuming every result came from Apify.

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

The request fields `provider_call_limit` and `dork_query_limit` may lower the configured ceilings but cannot raise them. The call budget counts logical operations reserved by the orchestrator; it is not a count of every HTTP request or provider-side polling request.

The explicitly requested platform reserves first, followed by explicit specialist inputs, inferred social candidates, configured AI correlation/risk calls, and finally SerpAPI dorks. Identical concurrent requests share one in-flight execution. Successful direct-provider reads are cached; failed or pending results are not.

The cache is process-local and in-memory. It is not Redis-backed and is cleared when the API process restarts. `cache_mode` supports:

- `use`: read a matching entry and store a miss.
- `refresh`: skip cache reads and replace the matching entry after completion.
- `bypass`: neither read nor store.

Telegram invite previews are always isolated, redacted, and uncached. They never fan out to search, database, AI, reporting, or non-Telegram providers.

## Runtime Modules

- `backend/main.py`: FastAPI application assembly, CORS, health checks, and routers.
- `backend/api/endpoints/investigation.py`: investigation orchestration, cache use, and provider budget enforcement.
- `backend/api/endpoints/providers.py`: explicit capability-provider routes.
- `backend/services/investigation_policy.py`: in-process TTL/LRU cache and call-budget primitives.
- `backend/services`: provider adapters and normalization.
- `backend/schemas`: request and response contracts.
- `backend/database`: SQL schema, ORM models, and migrations.

## Data and Trust Boundaries

- Provider adapters accept only the minimum target data needed for their capability.
- Bright Data and Firecrawl routes reject localhost, credentials in URLs, and private or reserved IP literals.
- Provider errors are bounded and normalized; secrets are not returned.
- Same-username results are identity candidates, not proof. Human corroboration is required.
- Only public or otherwise authorized data may be collected.

The editable Mermaid source is stored in `ARCHITECTURE_DIAGRAM.mmd`.
