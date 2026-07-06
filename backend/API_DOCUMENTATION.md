# AI-OSINT Platform API Documentation

Base URL: `http://localhost:8000`

FastAPI also exposes interactive documentation at `/docs` and OpenAPI JSON at `/openapi.json`.

## Root API Info

`GET /`

Returns a small JSON index with health, documentation, investigation, history, and report endpoint URLs.

## Health Check

`GET /health`

Returns service status, timestamp, and API version.

## Username Investigation

`POST /api/v1/investigation/username`

Request body:

```json
{
  "username": "example_user",
  "platform": "instagram",
  "case_id": "CASE-001",
  "correlation_depth": 2
}
```

Supported primary platforms are `instagram`, `twitter`, `telegram`, and `linkedin`.
The response includes a generated investigation ID, primary platform data, cross-platform matches, Google dorking results, AI correlation summary, database matches, hashtag analysis, and a risk assessment.

### Google Dorking Results

The investigation response includes `dorking_results`. When `SERPAPI_KEY` is configured, the backend runs approved public Google dork queries through SerpAPI first. If SerpAPI returns quota exhaustion, HTTP `429`, `402`, `403`, or a provider-specific quota/limit/credits error, the service automatically retries the query through Bright Data when `BRIGHTDATA_SERP_API_KEY` is configured. Results include normalized public search metadata grouped by category, provider metadata (`configured_providers`, `providers_used`, `fallback_used`, `failed_providers`, and provider failures), exact-match filtering to reduce similar-username noise, lightweight intelligence extraction, and a complex-dorking readiness flag. When no SERP key is configured, the response returns `status: not_configured` plus the prepared query list so local development remains deterministic.

Configure only the primary SerpAPI key and Bright Data fallback key; do not commit real values:

```env
SERPAPI_KEY=your-primary-serpapi-key
SERPAPI_BASE_URL=https://serpapi.com/search.json
SERPAPI_TIMEOUT_SECONDS=20
SERPAPI_RESULTS_PER_QUERY=5
BRIGHTDATA_SERP_API_KEY=your-brightdata-bearer-token
BRIGHTDATA_SERP_BASE_URL=https://api.brightdata.com/request
BRIGHTDATA_SERP_ZONE=serp_api1
BRIGHTDATA_SERP_TARGET_URL=https://www.google.com/search?q={query}
```

## Investigation History

- `GET /api/v1/investigation/history?limit=20&offset=0`
- `GET /api/v1/investigation/history/{investigation_id}`

The current implementation uses an in-memory store for development. Production deployments should connect these endpoints to PostgreSQL.

## Report Generation

`POST /api/v1/reports/generate-report/{investigation_id}?format=pdf`

Supported formats are `pdf` and `html`. The endpoint validates the investigation exists and returns the future report URL.

## RapidAPI FlashAPI Enrichment

Username investigations call FlashAPI as an enrichment provider and include the result under `platform_data.flashapi_enrichment`.

Required environment variables:

- `RAPIDAPI_KEY`
- `FLASHAPI_HOST` default: `flashapi1.p.rapidapi.com`
- `FLASHAPI_BASE_URL` default: `https://flashapi1.p.rapidapi.com`
- `FLASHAPI_ENDPOINT_PATH` default: `ig/info_username/`; `FLASHAPI_USERNAME_PARAM` default: `user`

When the RapidAPI key is missing, the API still works and returns a `not_configured` enrichment object for local development.

## Training Dataset

The backend can load the OSINT teammate training dataset from `final osint .json` at the repository root or from `backend/data/ai_training/final_osint.json`.

- `GET /api/v1/training/dataset/summary` returns dataset status, example count, categories, and confidence tiers.
- `GET /api/v1/training/dataset/examples/{example_id}` returns one training example.

Username investigations also include a lightweight `ai_correlation_result.training_context` object that references relevant dataset examples when the dataset file is present.


## Sprint 2 Integrations

Username investigations now include additional backend sections when configured:

- `ai_correlation_result.ai_analysis` uses DeepSeek when `DEEPSEEK_API_KEY` is set, otherwise returns a rules-based fallback.
- `risk_assessment.ai_risk_analysis` uses DeepSeek for risk review when configured.
- `internal_database_matches` searches the local SQLite `user_database` table by username, phone, and email.
- `hashtag_analysis` searches recent Twitter/X hashtag usage when Instagram hashtags and `TWITTER_BEARER_TOKEN` are available.

The Instagram service uses `instaloader` to return profile metadata, recent posts, hashtags, tagged users, business fields, and privacy/rate-limit status when public data is available.

## Instagram Catalog Coverage

The Instagram extractor is aligned with `docs/data_points_catalog-Instagram.csv` and returns stable keys for the catalog's high-priority username OSINT fields. Public/profile fields include username, display name, bio, profile image URLs, profile image hash, follower/following/post counts, verification/private/business status, account type, external URLs, business contact fields, recent post captions, hashtags, timestamps, locations, tagged users, mentioned users, pinned posts, collab posts, LinkedIn links in bio, and professional email hints.

Fields that are not reliably available through public Instagram scraping, such as direct messages, full follower/following lists, EXIF metadata, exact creation date, former usernames, active ads, tagged photos, comments made by subject, story highlights, and account country/region are returned as `null` where appropriate and explained in `catalog_coverage_notes`.

FlashAPI enrichment also normalizes provider fields into the main `platform_data` response when Instaloader fails but FlashAPI returns a valid Instagram user object, including related Instagram suggestions from `chaining_results` under `related_instagram_profiles`.
