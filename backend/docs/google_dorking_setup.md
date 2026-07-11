# Google Dorking Automation Setup

## Project Scope

This document describes the backend approach for automating public search-engine discovery with Google dorking and SerpAPI for OSINT, digital investigations, brand monitoring, and public profile discovery.

The service only collects public search-result metadata. It must not bypass logins, scrape private pages, or access non-public data.

## SERP Provider Setup

The backend tries configured providers in this order:

1. `SERPAPI_KEY` (primary SerpAPI key)
2. `BRIGHTDATA_SERP_API_KEY` (Bright Data SERP API fallback)
3. `APIFY_API_TOKEN` (Apify Google Search Results Scraper fallback)

If a provider is missing, times out, returns a non-success HTTP status, returns invalid payloads, or returns provider-specific quota/limit/credits errors, the service automatically tries the next configured provider. A successful provider response with zero organic matches does not trigger fallback. Do not commit real keys. Store them locally in `.env`:

Bright Data transport failures and transient HTTP responses (`408`, `425`, `429`, `500`, `502`, `503`, and `504`) are retried with bounded exponential backoff before the service moves to Apify. Failure metadata includes the attempt count, whether the status was retryable, provider response detail, and a request ID when Bright Data supplies one.

```env
SERPAPI_KEY=your_primary_serpapi_key
SERPAPI_BASE_URL=https://serpapi.com/search.json
SERPAPI_TIMEOUT_SECONDS=20
SERPAPI_RESULTS_PER_QUERY=5
BRIGHTDATA_SERP_API_KEY=your_brightdata_bearer_token
BRIGHTDATA_SERP_BASE_URL=https://api.brightdata.com/request
BRIGHTDATA_SERP_ZONE=serp_api1
BRIGHTDATA_SERP_TARGET_URL=https://www.google.com/search?q={query}
BRIGHTDATA_SERP_TIMEOUT_SECONDS=90
BRIGHTDATA_SERP_MAX_RETRIES=2
BRIGHTDATA_SERP_RETRY_BACKOFF_SECONDS=1.0
APIFY_API_TOKEN=your_apify_token
APIFY_SERP_TIMEOUT_SECONDS=120
```

## Backend Implementation

The implementation lives in:

```text
backend/services/google_dorking.py
```

It runs approved Indian-platform dork templates, calls the configured SERP provider chain, normalizes organic search results, filters close-but-not-exact username matches, deduplicates URLs, extracts lightweight intelligence, and groups results by category.

When no SERP provider key is configured, the service returns `status: not_configured` with the prepared queries so local development still works. When fallback happens, response metadata includes `provider_metadata.configured_providers`, `provider_metadata.providers_used`, `provider_metadata.fallback_used`, `provider_metadata.failed_providers`, and provider failure details.

The service is adapted from the standalone dorking engine idea for this repo:

- Search provider fallback now supports primary SerpAPI, Bright Data, and Apify through environment variables.
- Extra dependencies such as `duckduckgo_search`, `aiohttp`, and `BeautifulSoup` are intentionally not required.
- Indian-specific categories are included for professional, social, developer, education, ecommerce, forums, matrimony, blogs, and risk mentions.
- Exact-match filtering is applied so similar usernames do not appear as target matches.
- Complex/AI dorking is reported as a future phase until the current `AIAnalyzer` supports the needed entity-extraction methods.
- Compatibility wrappers named `execute_simple_dorking()` and `execute_complex_dorking()` are available so future code can call the supplied engine-style API without changing the current SerpAPI-backed implementation.

## Dork Categories

The backend implementation includes these categories:

- `professional`
- `social_media`
- `developer_tech`
- `education`
- `ecommerce`
- `forums`
- `matrimony`
- `blogs`
- `risk_mentions`

### Social Media Discovery

```text
"{username}" site:instagram.com
"{username}" site:x.com
"{username}" site:facebook.com
"{username}" site:t.me
"{username}" site:linkedin.com
"{username}" site:github.com
"{username}" site:reddit.com
"{username}" site:medium.com
"{username}" site:stackoverflow.com
"{username}" site:youtube.com
```

### Profile Discovery

```text
"{username}" intitle:"{username}"
"{username}" inurl:"{username}"
"{username}" "profile"
"{username}" "about me"
"{username}" "bio"
```

### Contact Discovery

```text
"{username}" "email"
"{username}" "contact"
"{username}" "website"
"{username}" "@gmail.com"
"{username}" "@outlook.com"
```

### Geographic Correlation

```text
"{username}" "location"
"{username}" "city"
"{username}" "country"
"{username}" "address"
"{username}" "university"
```

### Employment Correlation

```text
"{username}" "works at"
"{username}" "employee"
"{username}" "company"
"{username}" "organization"
"{username}" "team"
```

### Technical Attribution

```text
"{username}" site:github.com
"{username}" site:gitlab.com
"{username}" site:bitbucket.org
"{username}" site:npmjs.com
"{username}" site:pypi.org
```

### Document Discovery

```text
"{username}" filetype:pdf
"{username}" filetype:docx
"{username}" filetype:pptx
"{username}" filetype:xlsx
"{username}" ext:pdf
```

### Academic and Media Discovery

```text
"{username}" site:scholar.google.com
"{username}" site:researchgate.net
"{username}" site:orcid.org
"{username}" site:academia.edu
"{username}" site:youtube.com
"{username}" site:vimeo.com
"{username}" site:soundcloud.com
"{username}" site:spotify.com
```

## Investigation Workflow

```text
Target username
↓
Generate dork templates
↓
Execute ordered provider chain
↓
Collect public organic results
↓
Deduplicate URLs
↓
Group by category
↓
Return dorking_results in investigation response
```

## Output Shape

```json
{
  "provider": "serpapi",
  "status": "completed",
  "queries_run": 50,
  "result_count": 12,
  "results": [
    {
      "query": "\"target\" site:github.com",
      "category": "technical_attribution",
      "title": "Example result",
      "url": "https://github.com/target",
      "domain": "github.com",
      "snippet": "Public search snippet",
      "position": 1,
      "source": "google_serpapi",
      "serp_provider": "serpapi"
    }
  ],
  "grouped_by_category": {},
  "provider_metadata": {
    "configured_providers": ["serpapi", "brightdata", "apify"],
    "attempted_providers": ["serpapi", "brightdata"],
    "providers_used": ["brightdata"],
    "fallback_used": true,
    "failed_providers": ["serpapi"]
  }
}
```

## Limitations

- SERP providers have limited monthly searches/credits; configure backup providers to avoid hard failures when a primary quota is exhausted.
- Results depend on Google indexing and provider availability.
- Search snippets are not proof of identity; they need correlation and human review.
- Private, login-only, or legally restricted data must not be collected.
