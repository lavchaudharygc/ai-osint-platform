# Google Dorking Automation Setup

## Project Scope

This document describes the backend approach for automating public search-engine discovery with Google dorking and SerpAPI for OSINT, digital investigations, brand monitoring, and public profile discovery.

The service only collects public search-result metadata. It must not bypass logins, scrape private pages, or access non-public data.

## SerpAPI Setup

1. Create an account: <https://serpapi.com/users/sign_up>
2. Generate an API key: <https://serpapi.com/manage-api-key>
3. Store the key locally in `.env`:

```env
SERPAPI_KEY=your_api_key_here
SERPAPI_BASE_URL=https://serpapi.com/search.json
SERPAPI_TIMEOUT_SECONDS=20
SERPAPI_RESULTS_PER_QUERY=5
```

## Backend Implementation

The implementation lives in:

```text
backend/services/google_dorking.py
```

It runs approved Indian-platform dork templates, calls SerpAPI, normalizes organic search results, filters close-but-not-exact username matches, deduplicates URLs, extracts lightweight intelligence, and groups results by category.

When `SERPAPI_KEY` is missing, the service returns `status: not_configured` with the prepared queries so local development still works.

The service is adapted from the standalone dorking engine idea for this repo:

- Search provider remains SerpAPI, matching the existing backend configuration.
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
Execute SerpAPI searches
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
      "source": "google_serpapi"
    }
  ],
  "grouped_by_category": {}
}
```

## Limitations

- SerpAPI free tier has limited monthly searches.
- Results depend on Google indexing and SerpAPI availability.
- Search snippets are not proof of identity; they need correlation and human review.
- Private, login-only, or legally restricted data must not be collected.
