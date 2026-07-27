# Alternative Data Sources Research

> **Historical research catalog — non-operational.** The sources and code
> fragments below are analyst research notes, not enabled adapters, approved
> fallbacks, or an instruction to bypass access controls. The runtime uses the
> one-provider-per-capability mapping in `../API_DOCUMENTATION.md` and never
> switches to these sources automatically after a failure. Any manual use
> requires separate authorization, current legal/terms review, provenance, and
> case-level cost/privacy approval.

## Project Scope

This document evaluates alternative public data sources that can supplement Instagram investigations when direct platform access is unavailable, restricted, or incomplete.

Research period: Day 4–6  
Document version: 1.1

---

# 1. Search Engine Cache Sources

## Platform

Search engine cached pages and indexed snapshots.

## Primary Sources

| Service       | URL                                           |
| ------------- | --------------------------------------------- |
| Google Search | https://www.google.com/                       |
| Google Cache  | https://webcache.googleusercontent.com/       |
| Bing Search   | https://www.bing.com/                         |

## Capabilities

Cached pages may preserve:

* Previous profile biographies
* Historical usernames
* Website links
* Public profile descriptions
* Previously indexed public content references

## Example Queries

```text
site:instagram.com "username"
site:instagram.com "brand"
"username" instagram
site:instagram.com "example.com"
```

## Google Custom Search API

Documentation: https://developers.google.com/custom-search  
Endpoint: https://www.googleapis.com/customsearch/v1

```python
import requests

response = requests.get(
    "https://www.googleapis.com/customsearch/v1",
    params={
        "key": "API_KEY",
        "cx": "SEARCH_ENGINE_ID",
        "q": 'site:instagram.com "username"'
    }
)

print(response.json())
```

## Cache Lookup Example

```python
import requests
from urllib.parse import quote

def cache_lookup(url):
    cache_url = (
        "https://webcache.googleusercontent.com/search?q=cache:"
        + quote(url)
    )
    response = requests.get(cache_url, timeout=10)
    return response.text
```

## Advantages

* Publicly accessible
* No authentication required
* Useful for recently changed information

## Limitations

* Cache availability varies
* Information may be outdated
* Coverage is inconsistent

## Verdict

✅ One of the highest-value discovery techniques.

---

# 2. Internet Archive Research

## Platform

Wayback Machine — https://archive.org/  
API: https://archive.org/wayback/available  
Docs: https://archive.org/help/wayback_api.php

## Capabilities

Historical snapshots may contain:

* Previous biographies
* Historical profile layouts
* Earlier branding
* Website references
* Historical usernames

## Example Code

```python
import requests

def wayback_lookup(profile_url):
    response = requests.get(
        "https://archive.org/wayback/available",
        params={"url": profile_url}
    )
    return response.json()

result = wayback_lookup("https://instagram.com/instagram")
print(result)
```

## Additional Archive Sources

* Archive.today — https://archive.today/
* Common Crawl — https://commoncrawl.org/

## Advantages

* Historical preservation
* Long-term archives
* Public availability

## Limitations

* Incomplete coverage
* Dynamic content often missing
* Snapshot frequency varies

## Verdict

✅ Essential historical intelligence source.

---

# 3. Social Analytics Platforms

## SocialBlade

Website: https://socialblade.com/  
Instagram Example: https://socialblade.com/instagram/user/instagram

Available Information:

* Follower growth estimates
* Historical trends
* Ranking estimates
* Posting frequency

Verdict: ✅ Valuable analytics source.

---

## HypeAuditor

Website: https://hypeauditor.com/

Available Information:

* Engagement estimates
* Audience quality metrics
* Influencer analytics
* Audience authenticity estimates

Verdict: ✅ Useful for influencer investigations.

---

## Modash

Website: https://www.modash.io/

Available Information:

* Creator analytics
* Public engagement metrics
* Audience statistics

Verdict: ✅ Useful commercial analytics source.

---

# 4. Reverse Image Intelligence

| Service            | URL                              |
| ------------------ | -------------------------------- |
| Google Lens        | https://lens.google.com/         |
| Bing Visual Search | https://www.bing.com/visualsearch |
| Yandex Images      | https://yandex.com/images/       |

Applications:

* Cross-platform profile discovery
* Duplicate image detection
* Original upload discovery
* Media attribution

Verdict: ✅ Extremely valuable for profile correlation.

---

# 5. Metadata Analysis

## EXIF Metadata Example

```python
from PIL import Image

image = Image.open("image.jpg")
metadata = image.getexif()
print(metadata)
```

Potential Information:

* Camera model
* Capture timestamp
* Editing software
* GPS coordinates (if present)

## Tools

* ExifTool — https://exiftool.org/
* Pillow — https://pillow.readthedocs.io/

## Limitations

Most social media services strip metadata during upload.

Verdict: ⚠️ Useful but inconsistent.

---

# 6. Cross-Platform Identity Correlation

## Purpose

Many individuals reuse usernames across multiple services, enabling cross-platform discovery and attribution.

## Correlation Indicators

* Username reuse
* Shared profile images
* Similar biographies
* Shared websites
* Shared contact information
* Employer references

## Useful Platforms

| Platform       | URL                              |
| -------------- | -------------------------------- |
| GitHub         | https://github.com/              |
| LinkedIn       | https://www.linkedin.com/        |
| X              | https://x.com/                   |
| Reddit         | https://www.reddit.com/          |
| Medium         | https://medium.com/              |
| Stack Overflow | https://stackoverflow.com/       |
| Discord        | https://discord.com/             |

## Example Discovery Queries

```text
site:github.com "username"
site:linkedin.com/in "name"
"username" "website"
```

## Additional Discovery Sources

* Academic publications
* Conference speaker profiles
* Public code repositories
* Blog archives
* Press releases
* Company staff directories

Verdict: ✅ Critical for identity resolution.

---

# 7. Business and Infrastructure Intelligence

## Corporate Records

* OpenCorporates — https://opencorporates.com/ (company registrations, directors, corporate relationships)
* Crunchbase — https://www.crunchbase.com/ (business profiles, funding data)

## WHOIS / Domain Intelligence

| Service              | URL                            |
| -------------------- | ------------------------------ |
| ICANN WHOIS Lookup   | https://lookup.icann.org/      |
| WHO.IS               | https://who.is/                |
| SecurityTrails       | https://securitytrails.com/    |
| DNSDumpster          | https://dnsdumpster.com/       |
| ViewDNS              | https://viewdns.info/          |

Provides: domain registration dates, registrar info, DNS records, mail servers, subdomains, historical DNS changes.

## Certificate Transparency Logs

https://crt.sh/ — Useful for SSL certificate discovery, historical subdomains, and infrastructure mapping.

## Geospatial Intelligence

* OpenStreetMap — https://www.openstreetmap.org/
* Wikimapia — https://wikimapia.org/
* Google Maps — https://maps.google.com/

Verdict: ✅ Essential for infrastructure and organizational attribution.

---

# 8. Breach Intelligence and Exposure Monitoring

## Purpose

Breach intelligence platforms help determine whether publicly known data breaches contain identifiers associated with investigated assets.

Typical use cases:

* Defensive exposure monitoring
* Credential hygiene assessments
* Incident response
* Third-party risk assessment
* Organizational attack surface management

## Available Information

Depending on the provider:

* Email exposure history
* Breach names and dates
* Password hash exposure indicators
* Domain-wide breach notifications
* Credential reuse risks

## Recommended Services

### Have I Been Pwned

Website: https://haveibeenpwned.com/  
API Docs: https://haveibeenpwned.com/API/v3

```python
import requests

def check_breach(email, api_key):
    headers = {"hibp-api-key": api_key}
    response = requests.get(
        f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
        headers=headers
    )
    return response.status_code
```

Provides: email breach notifications, domain monitoring, paste exposure monitoring.

---

### DeHashed

Website: https://www.dehashed.com/

Provides: historical breach indexing, email exposure research, username correlation, domain intelligence.

---

### Intelligence X

Website: https://intelx.io/

Provides: historical web indexing, public document discovery, domain intelligence, historical website records.

---

### Hudson Rock

Website: https://www.hudsonrock.com/

Provides: infostealer exposure monitoring, credential exposure visibility, device compromise indicators.

---

## Limitations

* Availability varies by jurisdiction
* Some services require subscriptions
* Results should always be independently verified

Verdict: ✅ Valuable defensive security resource.

---

# 9. Confidence Scoring Model

| Score | Confidence                         |
| ----- | ---------------------------------- |
| 100   | Official source                    |
| 90    | Multiple independent confirmations |
| 75    | Strong public correlation          |
| 50    | Single source confirmation         |
| 25    | Weak indicator                     |
| 10    | Unverified claim                   |

---

# 10. Recommended Investigation Workflow

```text
Public Instagram Profile
            ↓
Search Engine Discovery
            ↓
Historical Archive Analysis
            ↓
Analytics Collection
            ↓
Reverse Image Correlation
            ↓
Cross-Platform Correlation
            ↓
Infrastructure & Business Intelligence
            ↓
Breach Intelligence Check
            ↓
Metadata Analysis
            ↓
Confidence Scoring
            ↓
Final Intelligence Report
```

---

# 11. Technology Stack Reference

| Category                | Tool                     |
| ----------------------- | ------------------------ |
| Search Discovery        | Google Search            |
| Historical Archives     | Wayback Machine          |
| Reverse Image Search    | Google Lens              |
| Analytics               | SocialBlade              |
| Audience Analytics      | HypeAuditor              |
| Metadata Analysis       | ExifTool / Pillow        |
| Breach Monitoring       | Have I Been Pwned        |
| Breach Intelligence     | Intelligence X           |
| Infrastructure Analysis | DNSDumpster              |
| Corporate Intelligence  | OpenCorporates           |
| Domain Intelligence     | SecurityTrails           |
| Username Correlation    | GitHub, LinkedIn, Reddit |

---

# 12. Analyst Validation Checklist

Before reporting findings:

* [ ] Verify with multiple independent sources
* [ ] Record collection timestamps
* [ ] Preserve source references
* [ ] Distinguish facts from assumptions
* [ ] Document confidence levels
* [ ] Re-check volatile information before publication

---

# Conclusion

Alternative data sources significantly improve visibility when platform APIs are limited or unavailable.

The most effective workflows combine:

1. Search engines
2. Historical archives
3. Analytics platforms
4. Reverse image analysis
5. Cross-platform verification
6. Infrastructure intelligence
7. Breach intelligence
8. Multiple-source validation

Confidence increases substantially when multiple independent public sources support the same finding.
