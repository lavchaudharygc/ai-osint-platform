# Google Dorking Automation Setup

## Project Scope

<<<<<<< HEAD
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

It runs approved dork templates, calls SerpAPI, normalizes organic search results, deduplicates URLs, and groups results by category.

When `SERPAPI_KEY` is missing, the service returns `status: not_configured` with the prepared queries so local development still works.

## Dork Categories

### Social Media Discovery
=======
This document evaluates methods for automating public search engine discovery using Google dorking techniques and search APIs for OSINT, digital investigations, brand monitoring, and public profile discovery.

Research period: Day 8
Document version: 1.0

---

# 1. SerpAPI Research

## Platform

SerpAPI

Website:

https://serpapi.com/

Documentation:

https://serpapi.com/search-api

---

## Overview

SerpAPI provides a structured API interface for Google Search and other search engines, allowing programmatic retrieval of publicly available search results without directly scraping search engine pages.

Supported search engines include:

* Google
* Bing
* Yahoo
* DuckDuckGo
* Baidu
* Yandex
* Google Images
* Google News
* Google Scholar

---

## Pricing

| Plan           | Searches                |
| -------------- | ----------------------- |
| Free Tier      | 100 searches/month      |
| Developer Plan | 5,000 searches/month    |
| Business Plans | Higher limits available |

---

## Setup Process

1. Create an account at:

```text
https://serpapi.com/users/sign_up
```

2. Generate an API key from:

```text
https://serpapi.com/manage-api-key
```

3. Store the key securely:

```env
SERPAPI_KEY=your_api_key_here
```

---

## Installation

```bash
pip install google-search-results
```

---

## Example Python Implementation

```python
from serpapi import GoogleSearch

params = {
    "q": 'openai site:github.com',
    "api_key": "SERPAPI_KEY"
}

search = GoogleSearch(params)

results = search.get_dict()

print(results)
```

---

## Example Environment Configuration

```env
SERPAPI_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## Advantages

* Structured JSON output
* Multiple search engine support
* Pagination support
* Geographic targeting
* Language targeting
* Image search support

---

## Limitations

* Monthly search quotas
* Costs increase with scale
* Dependent on third-party service availability

---

## Verdict

✅ Recommended for automated public search discovery workflows.

---

# 2. Google Dork Templates for OSINT

## Social Media Discovery
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

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

<<<<<<< HEAD
### Profile Discovery
=======
---

## Profile Discovery
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

```text
"{username}" intitle:"{username}"
"{username}" inurl:"{username}"
"{username}" "profile"
"{username}" "about me"
"{username}" "bio"
```

<<<<<<< HEAD
### Contact Discovery
=======
---

## Contact Discovery
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

```text
"{username}" "email"
"{username}" "contact"
"{username}" "website"
"{username}" "@gmail.com"
"{username}" "@outlook.com"
```

<<<<<<< HEAD
### Geographic Correlation
=======
---

## Geographic Correlation
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

```text
"{username}" "location"
"{username}" "city"
"{username}" "country"
"{username}" "address"
"{username}" "university"
```

<<<<<<< HEAD
### Employment Correlation
=======
---

## Employment Correlation
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

```text
"{username}" "works at"
"{username}" "employee"
"{username}" "company"
"{username}" "organization"
"{username}" "team"
```

<<<<<<< HEAD
### Technical Attribution
=======
---

## Technical Attribution
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

```text
"{username}" site:github.com
"{username}" site:gitlab.com
"{username}" site:bitbucket.org
"{username}" site:npmjs.com
"{username}" site:pypi.org
```

<<<<<<< HEAD
### Document Discovery
=======
---

## Document Discovery
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

```text
"{username}" filetype:pdf
"{username}" filetype:docx
"{username}" filetype:pptx
"{username}" filetype:xlsx
"{username}" ext:pdf
```

<<<<<<< HEAD
### Academic and Media Discovery
=======
---

## Academic Discovery
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf

```text
"{username}" site:scholar.google.com
"{username}" site:researchgate.net
"{username}" site:orcid.org
"{username}" site:academia.edu
<<<<<<< HEAD
=======
```

---

## Media Discovery

```text
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf
"{username}" site:youtube.com
"{username}" site:vimeo.com
"{username}" site:soundcloud.com
"{username}" site:spotify.com
```

<<<<<<< HEAD
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
=======
---

# 3. Example Automation Workflow

```text
Target Username
        ↓
Generate Dork Templates
        ↓
Execute Search Queries
        ↓
Collect Results
        ↓
Extract Candidate Profiles
        ↓
Cross Platform Correlation
        ↓
Confidence Scoring
        ↓
Final Investigation Report
```

---

# 4. Example Automation Code

```python
from serpapi import GoogleSearch

username = "target_username"

queries = [
    f'"{username}" site:instagram.com',
    f'"{username}" site:x.com',
    f'"{username}" site:github.com',
    f'"{username}" site:linkedin.com',
    f'"{username}" site:reddit.com'
]

for query in queries:
    params = {
        "engine": "google",
        "q": query,
        "api_key": "SERPAPI_KEY"
    }

    search = GoogleSearch(params)

    results = search.get_dict()

    print(results)
```

---

# 5. Recommended Technology Stack

| Category             | Tool                  |
| -------------------- | --------------------- |
| Search Automation    | SerpAPI               |
| Search Engine        | Google                |
| Image Discovery      | Google Images         |
| Reverse Image Search | Google Lens           |
| Historical Archives  | Wayback Machine       |
| Correlation Engine   | Custom Matching Logic |

---

# Conclusion

Search engine automation significantly improves public discovery workflows and reduces manual investigation effort.

The most effective workflows combine:

1. Search engine APIs.
2. Dork query templates.
3. Cross-platform verification.
4. Historical archives.
5. Multi-source validation.

Confidence increases substantially when findings are independently confirmed across multiple public sources.
>>>>>>> d07da9fc81636f7cd19e526ef817bd3c411907cf
