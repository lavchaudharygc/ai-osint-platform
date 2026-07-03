# Multi-Platform API Research

## Project Scope

This document evaluates official APIs and public interfaces across multiple platforms commonly encountered in OSINT investigations, brand monitoring, digital research, and public profile analysis.

Research period: Day 7
Document version: 1.0

---

# 1. Twitter/X API v2

## Platform

Twitter/X API v2

Documentation:

https://developer.x.com/en/docs

---

## Primary Endpoint

```text
GET https://api.twitter.com/2/users/by/username/:username
```

---

## Authentication

* Bearer Token Authentication
* OAuth 2.0 Supported
* OAuth 1.0a Supported for user-context operations

---

## Rate Limits

| Context       | Limit                     |
| ------------- | ------------------------- |
| User Lookup   | 300 requests / 15 minutes |
| Recent Search | Varies by plan            |
| Free Tier     | Limited monthly usage     |
| Enterprise    | Custom limits             |

---

## Public Data Available

* Username
* Display name
* Biography
* Profile image URL
* Followers count
* Following count
* Tweet count
* Verified status
* Account creation date
* Pinned tweet
* Location field
* Website URL

---

## Example Request

```http
GET https://api.twitter.com/2/users/by/username/openai
Authorization: Bearer YOUR_TOKEN
```

---

## Example Python Code

```python
import requests

headers = {
    "Authorization": "Bearer YOUR_TOKEN"
}

response = requests.get(
    "https://api.twitter.com/2/users/by/username/openai",
    headers=headers
)

print(response.json())
```

---

## Advantages

* Official API
* Structured JSON responses
* Stable schema
* High reliability

---

## Limitations

* Requires developer account
* Restricted free-tier access
* Historical access requires paid plans

---

## Verdict

✅ Recommended for official public profile collection.

---

# 2. Telegram Research

## Method 1: Public Username Pages

Public Telegram profiles can often be accessed via:

```text
https://t.me/username
```

Example:

```text
https://t.me/telegram
```

---

## Public Information Available

* Display name
* Username
* Public biography
* Profile image
* Public channel information
* Public member counts

---

## Method 2: MTProto API

Official Client API:

https://core.telegram.org/api

Python Library:

https://docs.telethon.dev/

---

## Authentication

* Phone number verification
* API ID
* API Hash

---

## Public Data Available

* Name
* Username
* Biography
* Profile photo
* Last seen visibility (if public)
* Public groups
* Public channels

---

## Example Telethon Code

```python
from telethon import TelegramClient

client = TelegramClient(
    "session",
    API_ID,
    API_HASH
)

client.start()

entity = client.get_entity("telegram")

print(entity.username)
print(entity.first_name)
```

---

## Rate Limits

Telegram does not publish strict limits but enforces:

* Flood protection
* Temporary restrictions
* Server-enforced cooldown periods

---

## Verdict

✅ Excellent source for public channel and community analysis.

---

# 3. GitHub API Research

## Platform

GitHub REST API

Documentation:

https://docs.github.com/en/rest

---

## Endpoint

```text
GET https://api.github.com/users/:username
```

Example:

```text
https://api.github.com/users/octocat
```

---

## Rate Limits

| Authentication  | Limit              |
| --------------- | ------------------ |
| Unauthenticated | 60 requests/hour   |
| Authenticated   | 5000 requests/hour |

---

## Public Data Available

* Username
* Name
* Biography
* Company
* Website
* Location
* Public repositories
* Followers
* Following
* Organizations
* Repository stars
* Repository forks
* Languages used
* Contribution history

---

## Example Code

```python
import requests

response = requests.get(
    "https://api.github.com/users/octocat"
)

print(response.json())
```

---

## Advantages

* Generous rate limits
* Rich public profile data
* Excellent documentation
* Stable API

---

## Verdict

✅ One of the highest-value APIs for technical attribution and identity correlation.

---

# 4. Reddit API Research

## Platform

Reddit API

Documentation:

https://www.reddit.com/dev/api/

---

## Endpoint

```text
GET https://reddit.com/user/:username/about.json
```

Example:

```text
https://reddit.com/user/spez/about.json
```

---

## Rate Limits

| Limit Type | Value              |
| ---------- | ------------------ |
| Requests   | 60 requests/minute |

---

## Public Data Available

* Username
* Account age
* Link karma
* Comment karma
* Trophy information
* Verified email status
* Premium status
* Active communities
* Public posts
* Public comments

---

## Example Code

```python
import requests

headers = {
    "User-Agent": "research-client"
}

response = requests.get(
    "https://reddit.com/user/spez/about.json",
    headers=headers
)

print(response.json())
```

---

## Advantages

* Public JSON endpoints
* Rich community activity history
* Historical posting visibility

---

## Limitations

* Requires User-Agent header
* Rate limits enforced
* Deleted content unavailable

---

## Verdict

✅ Extremely valuable for behavioral analysis and community attribution.

---

# 5. Recommended Cross-Platform Collection Workflow

```text
Username
    ↓
Twitter/X Lookup
    ↓
GitHub Lookup
    ↓
Reddit Lookup
    ↓
Telegram Lookup
    ↓
Cross Platform Correlation
    ↓
Confidence Scoring
    ↓
Final Intelligence Report
```

---

# 6. Recommended Technology Stack

| Category               | Tool                  |
| ---------------------- | --------------------- |
| Microblogging          | Twitter/X API         |
| Messaging              | Telegram MTProto      |
| Developer Intelligence | GitHub API            |
| Community Intelligence | Reddit API            |
| Correlation Engine     | Custom Matching Logic |

---

# Conclusion

No single platform provides complete visibility into a user's public online presence.

The most effective investigations combine:

1. Official APIs.
2. Public profile information.
3. Cross-platform correlation.
4. Historical analysis.
5. Multi-source validation.

Confidence increases significantly when multiple independent platforms support the same attribution.
