# Instagram Platform Behavior — OSINT Data Extraction Reference

**Prepared by:** Shubham Jha
**Date:** 28 June 2026
**Sprint:** Sprint 1
**Reference:** Instagram Data Points Catalog (40 Points)

---

## 1. Purpose

This document describes Instagram's platform behavior relevant to OSINT data extraction. It covers URL structure, public vs. private visibility, rate limits, anti-scraping measures, error handling, and Indian user-specific patterns. It is intended for developers implementing robust data-fetching logic without crashes or blocks.

---

## 2. Instagram Profile URL Structure

**Standard format:**
```
https://www.instagram.com/{username}/
```

**Rules:**
- Username is case-insensitive in the URL but stored as lowercase
- Maximum 30 characters
- Allowed characters: letters (a-z), numbers (0-9), underscore (_), period (.)
- Period cannot appear at the start or end
- Consecutive periods are not allowed

**Examples:**

| URL | Valid |
|---|---|
| `https://www.instagram.com/lavkumar_ig/` | Yes |
| `https://www.instagram.com/test.user.2024/` | Yes |
| `https://www.instagram.com/.test_user/` | No — leading dot |
| `https://www.instagram.com/test..user/` | No — consecutive dots |

---

## 3. Data Visibility Matrix

| # | Data Point | Public Account | Private Account | Business Account | Notes |
|---|---|---|---|---|---|
| 1 | Username | Always | Always | Always | Primary identifier |
| 2 | Full Name | Always | Always | Always | Display name, can be anything |
| 3 | Bio Text | Always | Always | Always | Max 150 characters |
| 4 | Profile Picture | Always | Always | Always | Downloadable via URL |
| 5 | Followers Count | Always | Always | Always | Shown publicly |
| 6 | Following Count | Always | Always | Always | Shown publicly |
| 7 | Post Count | Always | Always | Always | Total post count visible |
| 8 | External URL | Always | Always | Always | Single clickable link in bio |
| 9 | Verified Badge | Always | Always | Always | Blue tick visible |
| 10 | Business Category | If business | No (personal) | Always | e.g. "Product/Service" |
| 11 | Account Creation Date | Estimate only | Estimate only | Estimate only | Not directly exposed; check first post |
| 12 | Post Captions | Full access | Blocked | Full access | Public posts only |
| 13 | Post Hashtags | Extractable | Blocked | Extractable | From caption text |
| 14 | Post Timestamps | Extractable | Blocked | Extractable | ISO format |
| 15 | Post Location Tags | If tagged | Blocked | If tagged | User must opt in |
| 16 | Tagged Users in Posts | Extractable | Blocked | Extractable | From post metadata |
| 17 | Mentioned Users | From captions | Blocked | From captions | @username in text |
| 18 | Comments Made | Hard to scrape | Blocked | Hard to scrape | Rate limited, needs login |
| 19 | Tagged Photos | Privacy dependent | Blocked | Privacy dependent | Depends on tag review settings |
| 20 | Profile Picture Hash | Computable | Computable | Computable | pHash from downloaded image |
| 21 | Linked Facebook Account | Not always visible | Hidden | Sometimes visible | In "Accounts Center" |
| 22 | Story Highlights | Titles public | Titles public | Titles public | Content inside is public |
| 23 | Reels/IGTV Count | Visible | Visible | Visible | Tab count on profile |
| 24 | Account Country | Estimate only | Estimate only | Estimate only | From About section if available |
| 25 | Former Usernames | If not hidden | If not hidden | If not hidden | About → Former Usernames |
| 26 | Active Ads | If running | Hidden | If running | About → Active Ads |
| 27 | Account Type | Visible | Visible | Visible | Personal/Creator/Business |
| 28 | Contact Email | No (personal) | Hidden | If provided | Business/Creator only |
| 29 | Contact Phone | No (personal) | Hidden | If provided | Business/Creator only |
| 30 | Contact Address | No (personal) | Hidden | If provided | Business/Creator only |
| 31 | Pinned Posts | Visible | Blocked | Visible | Top 3 posts on grid |
| 32 | Collab Posts | Hard | Blocked | Hard | Needs post metadata |
| 33 | Story Replies | Not accessible | Not accessible | Not accessible | Only while story is live, and requires login |
| 34 | Followers List | Not accessible | Not accessible | Not accessible | Rate limited, login required |
| 35 | Following List | Not accessible | Not accessible | Not accessible | Rate limited, login required |
| 36 | Likes on Others' Posts | Not accessible | Not accessible | Not accessible | Not publicly available |
| 37 | EXIF Metadata | Not accessible | Not accessible | Not accessible | Instagram strips EXIF post-2012 |
| 38 | DM Content | Not accessible | Not accessible | Not accessible | Requires court order |
| 39 | LinkedIn Link | If in bio | If in bio | If in bio | Scrape from bio text |
| 40 | Professional Email | If in bio | If in bio | If in bio | Regex extraction from bio |

---

## 4. Rate Limiting Patterns

**Observed limits (from testing):**

| Action | Limit | Time Window | Consequence |
|---|---|---|---|
| Profile page requests | ~200 | Per hour | IP blocked for 30 min |
| Post content fetch | ~100 | Per hour | Throttled, slower responses |
| Image download | ~500 | Per hour | CDN blocks temporarily |
| Search queries | ~50 | Per hour | Rate limit error |
| Login attempts | ~5 | Per 10 minutes | Account locked temporarily |

**Recommended delays:**

| Scenario | Delay |
|---|---|
| Between profile requests | 3–7 seconds (random) |
| Between post fetches | 2–5 seconds (random) |
| After rate limit hit | Wait 30 minutes minimum |
| After IP block | Switch IP or wait 1 hour |

**Rate limit detection signals:**
- HTTP 429 "Too Many Requests"
- Response contains `challenge_required`
- Redirect to login page
- Empty response body
- Response time suddenly exceeds 30 seconds

---

## 5. Anti-Scraping Measures

**Instagram's defense layers:**

| Layer | What Happens | How to Handle |
|---|---|---|
| 1 — Rate Limit | 429 errors after ~200 req/hr | Add delays, rotate IPs |
| 2 — Login Wall | Redirects to login page | Use saved session cookies |
| 3 — Challenge Page | CAPTCHA or "suspicious activity" | Wait 24–48 hours, reduce frequency |
| 4 — IP Block | Complete access denied | Use proxy/VPN, wait longer |
| 5 — Account Block | Account flagged | Use different account, appeal |

**Bypass strategies (priority order):**
1. **Session persistence** — save login session file, reuse across runs
2. **Random delays** — never use fixed delays, always randomize 3–7 seconds
3. **User-agent rotation** — use real browser user-agents
4. **Request headers** — include proper Referer, Accept-Language, etc.
5. **Proxy rotation** — rotate IPs for bulk extraction (LEA-authorized use only)

---

## 6. Error Handling — Complete Reference

| Error Type | Meaning | Developer Action |
|---|---|---|
| `ProfileNotExistsException` | Username does not exist | Return error: "Profile not found" |
| `PrivateProfileNotFollowedException` | Account is private | Return limited data, `is_private=true` |
| `RateLimitExceeded` (429) | Too many requests | Wait 30 min, retry |
| `LoginRequiredException` | Login wall hit | Load session or prompt for login |
| `ChallengeRequiredException` | CAPTCHA triggered | Notify user, wait 24 hours |
| `ConnectionError` | Network issue | Retry 3x with exponential backoff |
| `QueryReturnedNotFoundException` (404) | Invalid query | Validate username format before request |
| `BadCredentialsException` (401) | Login failed | Check credentials, notify user |
| `TwoFactorAuthRequiredException` | 2FA enabled | Not supported — use session file |

**Error response format (for frontend):**
```json
{
  "error": true,
  "error_type": "RATE_LIMITED",
  "message": "Too many requests. Please wait 30 minutes.",
  "retry_after_seconds": 1800,
  "username": "test_user",
  "timestamp": "2026-06-28T14:30:00Z"
}
```

---

## 7. Indian User Behavior Patterns

**Common patterns observed:**

| Pattern | Example | OSINT Value |
|---|---|---|
| Phone in bio | "Call: 9876543210" / "WA: +91 98765 43210" | Direct identifier — Rule #2 |
| Hindi/Devanagari bio | "नमस्ते! मैं दिल्ली से हूँ" | Requires UTF-8 handling |
| Hinglish mix | "Delhi ka photographer hu, travel lover" | Stylometric analysis — Rule #14 |
| Multiple platform links | "Twitter: @xyz | Snap: xyz_snap | YT: xyz" | Cross-platform discovery |
| Linktree/Bio.link | "linktr.ee/username" | Single click reveals 4–6 platforms — Rule #16 |
| Business WhatsApp | "Business inquiries: WA +91 98XXX" | WhatsApp not directly scrapable |
| Location in bio | "Mumbai / Pune / India" | Geocoding — Rule #9 |
| Email in bio | "Collab: email@gmail.com" | Direct identifier — Rule #3 |
| College/university | "DU'24 | IITian | NMIMS" | Education verification — cross-reference with LinkedIn |

**Phone number formats found in Indian bios:**

| Original in Bio | Normalized |
|---|---|
| "Call: 9876543210" | 9876543210 |
| "+91 98765 43210" | 9876543210 |
| "09876543210" | 9876543210 |
| "98765-43210" | 9876543210 |
| "+91-98765-43210" | 9876543210 |

Regex for Indian mobile numbers: `[6-9]\d{9}` (after stripping `+91`, leading `0`, spaces, and dashes)

---

## 8. Data Extraction — P0 Sequence

**Recommended extraction order (fastest to slowest):**

| Step | Speed | Data Points |
|---|---|---|
| 1 | Instant | Username, Full Name, Bio, Profile Pic URL, Verified Status |
| 2 | Instant | Follower Count, Following Count, Post Count, Account Type |
| 3 | Fast | External URL, Business Category, Contact Info (if Business) |
| 4 | Medium | Last 12 Posts — Captions + Hashtags |
| 5 | Medium | Post Timestamps, Location Tags, Tagged Users |
| 6 | Slow | Profile Picture Download + pHash computation |
| 7 | Optional | Comments, Tagged Photos, Story Highlights |

**Parallel processing where possible:**
- Can run in parallel: Step 1 + Step 2 (independent data)
- Can run in parallel: Profile pic download + Post fetch (different endpoints)
- Must run sequentially: Post fetch → hashtag extraction (dependency)

---

## 9. Data Integrity & Validation

**Checks before storing:**

| Data Point | Validation Rule |
|---|---|
| Username | Must match input (case-insensitive) |
| Full Name | Not empty, not "Instagram User" (default) |
| Follower Count | Must be integer ≥ 0 |
| Following Count | Must be integer ≥ 0 |
| Post Count | Must be integer ≥ 0 |
| Profile Pic URL | Must return HTTP 200 |
| Bio | Can be empty string (valid) |
| External URL | If present, must start with `http` |

---

## 10. Fallback Sources

**When Instagram blocks access:**

| Source | What It Provides | Limitation |
|---|---|---|
| Google Cache | Last indexed version of profile | May be outdated (days/weeks) |
| Wayback Machine | Historical profile snapshots | Not real-time |
| Social Blade | Follower count history | No bio/posts |
| Google Dorks | `site:instagram.com "username"` | Search result snippets only |

**Fallback order:**
1. Instagram direct (primary)
2. Google Cache (if primary blocked)
3. Wayback Machine (if Google Cache empty)
4. Google Dorks (last resort — limited data)

---

## 11. Legal Boundaries — India

**Under IT Act 2000:**

| Section | Relevance |
|---|---|
| Section 69 | Government can intercept/monitor for national security |
| Section 69B | Monitor traffic for cyber security incidents |
| Section 72A | Punishment for disclosure of information without consent |

**Key rules for developers:**
- Public data scraping is legal (publicly accessible information)
- Private account data requires legal process (court order)
- DM content is never accessible without a court order
- Instagram EXIF data is not available (stripped by platform)
- Data collected must have an audit trail (Section 65B, Evidence Act)
- All investigations must be logged with timestamp and officer ID

---

## 12. Summary — Developer Quick Reference

| Question | Answer |
|---|---|
| Max requests per hour? | ~200, then 30-min block |
| Delay between requests? | Random 3–7 seconds |
| Login needed? | Session file recommended, not required for public data |
| Private account data? | Only username, name, bio, pic — no posts |
| Non-existent user? | Return clear error, no crash |
| Indian phone regex? | `[6-9]\d{9}` after normalization |
| Hindi text handling? | UTF-8, NFC normalization, preserve all characters |
| Business contact info? | Available for Business/Creator accounts only |
| Profile pic matching? | pHash for exact match; face embedding for filtered images |
| Error format? | JSON with `error_type`, `message`, `retry_after` |
| Audit required? | Yes — log all investigations per IT Act |

---

*End of document*
