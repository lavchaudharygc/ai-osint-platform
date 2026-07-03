# Google Dorking Automation Setup

## Project Scope

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

---

## Profile Discovery

```text
"{username}" intitle:"{username}"
"{username}" inurl:"{username}"
"{username}" "profile"
"{username}" "about me"
"{username}" "bio"
```

---

## Contact Discovery

```text
"{username}" "email"
"{username}" "contact"
"{username}" "website"
"{username}" "@gmail.com"
"{username}" "@outlook.com"
```

---

## Geographic Correlation

```text
"{username}" "location"
"{username}" "city"
"{username}" "country"
"{username}" "address"
"{username}" "university"
```

---

## Employment Correlation

```text
"{username}" "works at"
"{username}" "employee"
"{username}" "company"
"{username}" "organization"
"{username}" "team"
```

---

## Technical Attribution

```text
"{username}" site:github.com
"{username}" site:gitlab.com
"{username}" site:bitbucket.org
"{username}" site:npmjs.com
"{username}" site:pypi.org
```

---

## Document Discovery

```text
"{username}" filetype:pdf
"{username}" filetype:docx
"{username}" filetype:pptx
"{username}" filetype:xlsx
"{username}" ext:pdf
```

---

## Academic Discovery

```text
"{username}" site:scholar.google.com
"{username}" site:researchgate.net
"{username}" site:orcid.org
"{username}" site:academia.edu
```

---

## Media Discovery

```text
"{username}" site:youtube.com
"{username}" site:vimeo.com
"{username}" site:soundcloud.com
"{username}" site:spotify.com
```

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
