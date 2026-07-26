# Google Dorking Automation Setup

## Scope

The backend automates public search-engine discovery for authorized OSINT work. It collects public organic-result metadata and does not bypass logins or access private content.

## Provider Policy: SerpAPI Only

Google search is routed exclusively to SerpAPI. Bright Data is reserved for general web pages and LinkedIn, while Apify is reserved for the approved social Actors. There is no Bright Data or Apify SERP fallback.

If SerpAPI is missing, fails, times out, reaches quota, or returns invalid data, the service returns `not_configured`, `failed`, or `completed_with_errors` as appropriate. It does not call a second provider. `provider_metadata.fallback_used` is therefore always `false`.

Configure SerpAPI in `backend/.env`:

```env
SERPAPI_KEY=your-serpapi-key
SERPAPI_BASE_URL=https://serpapi.com/search.json
SERPAPI_TIMEOUT_SECONDS=20
SERPAPI_RESULTS_PER_QUERY=5
```

Do not commit real credentials. `backend/.env.example` is a copy-only template; runtime configuration is loaded from `backend/.env` and then overridden by process environment variables when present.

## Query and Cost Limits

The user-facing investigation and provider routes apply `INVESTIGATION_MAX_DORK_QUERIES`, which defaults to `10`. Each dork query consumes one logical unit from the investigation's overall `INVESTIGATION_MAX_PROVIDER_CALLS` budget, which defaults to `24`.

```env
INVESTIGATION_MAX_DORK_QUERIES=10
INVESTIGATION_MAX_PROVIDER_CALLS=24
```

For `POST /api/v1/investigation/username`, `dork_query_limit` may lower the configured query ceiling. For `POST /api/v1/providers/search/username`, the request `limit` is also clamped to the configured ceiling. Setting an investigation's `dork_query_limit` to `0` skips SerpAPI.

## API Usage

Use the explicit route when only search is needed:

```http
POST /api/v1/providers/search/username
Content-Type: application/json

{
  "username": "target_user",
  "full_name": "Target User",
  "limit": 5
}
```

Username investigations include the same search output under `dorking_results` and a summary under `provider_results.search`.

## Implementation

The implementation lives in `backend/services/google_dorking.py`. It:

- builds approved Indian and global platform dork templates;
- caps the executed batch;
- sends each query to SerpAPI;
- normalizes organic results;
- filters close-but-not-exact username matches;
- deduplicates URLs;
- groups results by category; and
- extracts lightweight profile, email, phone, location, organization, and document clues.

When `SERPAPI_KEY` is absent, the service returns the prepared queries so local development remains deterministic, but no external request is sent.

## Dork Categories

- `professional`
- `social_media`
- `developer_tech`
- `education`
- `ecommerce`
- `forums`
- `matrimony`
- `blogs`
- `risk_mentions`
- `username_variation`

Representative templates include:

```text
site:linkedin.com/in "{username}"
site:instagram.com "{username}"
site:twitter.com "{username}" OR site:x.com "{username}"
site:github.com "{username}"
"{username}" "scam"
"{full_name}" filetype:pdf "result" site:ac.in
```

## Workflow

```text
Target username
  -> generate bounded dork batch
  -> reserve provider-call units
  -> execute through SerpAPI only
  -> normalize and exact-match filter
  -> deduplicate and group
  -> return dorking_results
```

## Output Shape

```json
{
  "provider": "serpapi",
  "status": "completed",
  "phase": "simple_dorking",
  "queries_run": 5,
  "result_count": 1,
  "results": [
    {
      "query": "site:github.com \"target_user\"",
      "category": "developer_tech",
      "title": "Example result",
      "url": "https://github.com/target_user",
      "domain": "github.com",
      "snippet": "Public search snippet",
      "position": 1,
      "source": "google_serpapi",
      "serp_provider": "serpapi"
    }
  ],
  "grouped_by_category": {},
  "provider_metadata": {
    "configured_providers": ["serpapi"],
    "attempted_providers": ["serpapi"],
    "providers_used": ["serpapi"],
    "fallback_used": false,
    "failed_providers": [],
    "disabled_providers": [],
    "provider_failures": []
  }
}
```

## Limitations

- SerpAPI quota is finite. Reduce `INVESTIGATION_MAX_DORK_QUERIES` for lower-cost deployments.
- Search results depend on Google indexing and SerpAPI availability.
- Search snippets and username similarity are not proof of identity.
- Private, login-only, or legally restricted data must not be collected.
