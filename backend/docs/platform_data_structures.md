# Instagram Platform Data Structures

## Project Scope

This document describes the data structures, field definitions, and object models used by the Instagram platform, including the Graph API response formats and internal data representations relevant to data collection workflows.

Research period: Day 4–6  
Document version: 1.0

---

# 1. User / Profile Object

## Fields

| Field                  | Type    | Description                                      |
| ---------------------- | ------- | ------------------------------------------------ |
| `id`                   | string  | Unique Instagram user ID                         |
| `username`             | string  | Public username                                  |
| `name`                 | string  | Display name                                     |
| `biography`            | string  | Profile biography text                           |
| `website`              | string  | External URL listed on profile                   |
| `profile_picture_url`  | string  | URL of profile picture                           |
| `followers_count`      | integer | Number of followers                              |
| `follows_count`        | integer | Number of accounts followed                      |
| `media_count`          | integer | Total number of public posts                     |
| `account_type`         | string  | `PERSONAL`, `BUSINESS`, or `MEDIA_CREATOR`       |
| `is_private`           | boolean | Whether the account is private                   |
| `is_verified`          | boolean | Whether the account has a verified badge         |

## Example (Graph API)

```json
{
  "id": "17841400008460056",
  "username": "instagram",
  "name": "Instagram",
  "biography": "Discover what's new on Instagram.",
  "website": "https://about.instagram.com/",
  "followers_count": 600000000,
  "follows_count": 500,
  "media_count": 1200,
  "account_type": "BUSINESS",
  "is_verified": true,
  "is_private": false
}
```

---

# 2. Media Object

## Fields

| Field          | Type    | Description                                        |
| -------------- | ------- | -------------------------------------------------- |
| `id`           | string  | Unique media ID                                    |
| `shortcode`    | string  | URL shortcode (used in `instagram.com/p/<code>`)   |
| `media_type`   | string  | `IMAGE`, `VIDEO`, or `CAROUSEL_ALBUM`              |
| `caption`      | string  | Post caption text                                  |
| `like_count`   | integer | Number of likes                                    |
| `comments_count` | integer | Number of comments                               |
| `timestamp`    | string  | ISO 8601 creation timestamp                        |
| `permalink`    | string  | Full URL to the post                               |
| `media_url`    | string  | URL to the media file                              |
| `thumbnail_url`| string  | Thumbnail URL (video posts only)                   |
| `owner`        | object  | Partial user object (`id`, `username`)             |

## Example (Graph API)

```json
{
  "id": "17854360229135492",
  "shortcode": "CxYz1234ABC",
  "media_type": "IMAGE",
  "caption": "Explore more with Instagram.",
  "like_count": 42000,
  "comments_count": 310,
  "timestamp": "2024-03-15T12:00:00+0000",
  "permalink": "https://www.instagram.com/p/CxYz1234ABC/",
  "media_url": "https://cdn.instagram.com/image.jpg",
  "owner": {
    "id": "17841400008460056",
    "username": "instagram"
  }
}
```

---

# 3. Comment Object

## Fields

| Field       | Type    | Description                          |
| ----------- | ------- | ------------------------------------ |
| `id`        | string  | Unique comment ID                    |
| `text`      | string  | Comment text                         |
| `timestamp` | string  | ISO 8601 creation timestamp          |
| `username`  | string  | Username of commenter                |
| `like_count`| integer | Number of likes on the comment       |
| `replies`   | array   | Nested reply objects (if any)        |

## Example

```json
{
  "id": "17858893269000001",
  "text": "Amazing post!",
  "timestamp": "2024-03-15T13:45:00+0000",
  "username": "user123",
  "like_count": 5,
  "replies": []
}
```

---

# 4. Hashtag Object

## Fields

| Field          | Type    | Description                         |
| -------------- | ------- | ----------------------------------- |
| `id`           | string  | Unique hashtag ID                   |
| `name`         | string  | Hashtag text (without `#`)          |
| `media_count`  | integer | Approximate number of tagged posts  |

## Example

```json
{
  "id": "17873440040125421",
  "name": "photography",
  "media_count": 850000000
}
```

---

# 5. Location Object

## Fields

| Field       | Type   | Description                   |
| ----------- | ------ | ----------------------------- |
| `id`        | string | Unique location ID            |
| `name`      | string | Location display name         |
| `city`      | string | City name (if available)      |
| `country`   | string | Country name (if available)   |
| `latitude`  | float  | Latitude coordinate           |
| `longitude` | float  | Longitude coordinate          |

## Example

```json
{
  "id": "213385402",
  "name": "New York, New York",
  "city": "New York",
  "country": "United States",
  "latitude": 40.7128,
  "longitude": -74.0060
}
```

---

# 6. Story Object

## Fields

| Field         | Type    | Description                              |
| ------------- | ------- | ---------------------------------------- |
| `id`          | string  | Unique story ID                          |
| `media_type`  | string  | `IMAGE` or `VIDEO`                       |
| `media_url`   | string  | URL to the story media file              |
| `timestamp`   | string  | ISO 8601 creation timestamp              |
| `expire_time` | string  | ISO 8601 expiry timestamp (24h from post)|

## Notes

* Stories expire after 24 hours.
* Only accessible for authorized accounts via the Graph API.
* Not available for public scraping.

---

# 7. Graph API Pagination

The Graph API uses cursor-based pagination for collections.

## Pagination Object

```json
{
  "data": [...],
  "paging": {
    "cursors": {
      "before": "cursor_string_before",
      "after": "cursor_string_after"
    },
    "next": "https://graph.facebook.com/...",
    "previous": "https://graph.facebook.com/..."
  }
}
```

## Usage

```python
import requests

def fetch_paginated(url, params):
    results = []
    while url:
        response = requests.get(url, params=params)
        data = response.json()
        results.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = {}  # cursor is embedded in next URL
    return results
```

---

# 8. Local Database Schema

Used by the collection tool (`app.py`) to store collected data.

## Profiles Table

```sql
CREATE TABLE IF NOT EXISTS profiles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT UNIQUE,
    user_id           TEXT,
    full_name         TEXT,
    biography         TEXT,
    followers         INTEGER,
    following         INTEGER,
    posts             INTEGER,
    profile_pic_url   TEXT,
    external_url      TEXT,
    business_category TEXT,
    is_private        BOOLEAN,
    is_verified       BOOLEAN,
    date_collected    TEXT,
    source_method     TEXT
);
```

## Media Table

```sql
CREATE TABLE IF NOT EXISTS media (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        TEXT,
    media_id       TEXT,
    media_type     TEXT,
    caption        TEXT,
    likes          INTEGER,
    comments       INTEGER,
    timestamp      TEXT,
    location_name  TEXT,
    tags           TEXT,
    date_collected TEXT,
    source_method  TEXT
);
```

---

# 9. Field Availability by Collection Method

| Field            | Graph API | Instaloader | Web Scraping |
| ---------------- | --------- | ----------- | ------------ |
| Username         | ✅        | ✅          | ✅           |
| Full Name        | ✅        | ✅          | ✅           |
| Biography        | ✅        | ✅          | ✅           |
| Followers Count  | ✅        | ✅          | ⚠️ Partial  |
| Following Count  | ✅        | ✅          | ⚠️ Partial  |
| Post Count       | ✅        | ✅          | ⚠️ Partial  |
| Profile Picture  | ✅        | ✅          | ✅           |
| External URL     | ✅        | ✅          | ⚠️ Partial  |
| Is Verified      | ✅        | ✅          | ⚠️ Partial  |
| Is Private       | ✅        | ✅          | ✅           |
| Media Captions   | ✅        | ✅          | ❌           |
| Like Count       | ✅        | ✅          | ❌           |
| Comment Count    | ✅        | ✅          | ❌           |
| Story Content    | ✅        | ⚠️ Auth    | ❌           |
| Followers List   | ❌        | ⚠️ Auth    | ⚠️ Auth     |

Legend: ✅ Available · ⚠️ Partial / Auth required · ❌ Not available

---

# Conclusion

Understanding the platform data structures ensures collected data is properly normalized and stored. The local SQLite schema in `app.py` mirrors the most commonly available public fields, with collection method tracked per record for traceability.
