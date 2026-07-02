# Twitter/X Platform Behavior — OSINT Data Extraction Reference

**Prepared by:** Shubham Jha
**Date:** 02 July 2026
**Sprint:** Sprint 1
**Reference:** Twitter/X Data Points Catalog

---

## 1. Purpose

This document describes Twitter/X's platform behavior relevant to OSINT data extraction. It covers URL structure, public vs. protected visibility, rate limits, anti-scraping measures, error handling, and Indian user-specific patterns. It is intended for developers implementing robust data-fetching logic without crashes or blocks.

---

## 2. Twitter/X Profile URL Structure

**Standard format:**
```
https://x.com/{username}
https://twitter.com/{username}
```

**Rules:**
- Username (handle) is case-insensitive, stored internally as entered but matched case-insensitively
- Maximum 15 characters
- Allowed characters: letters (a-z, A-Z), numbers (0-9), underscore (_)
- No periods allowed
- Cannot start with a number-only string that resembles a reserved pattern
- Reserved/system words (e.g. `home`, `settings`, `explore`) cannot be used as handles

**Examples:**

| URL | Valid |
|---|---|
| `https://x.com/shubham_jha` | Yes |
| `https://x.com/user_2024` | Yes |
| `https://x.com/user.name` | No — period not allowed |
| `https://x.com/this_handle_is_too_long` | No — exceeds 15 characters |

**Note:** `twitter.com` links still resolve and redirect to `x.com`; both should be normalized to the same canonical form during data collection.

---

## 3. Data Visibility Matrix

| # | Data Point | Public Account | Protected Account | Verified (Blue/Gold) | Notes |
|---|---|---|---|---|---|
| 1 | Username/Handle | Always | Always | Always | Primary identifier |
| 2 | Display Name | Always | Always | Always | Can be changed freely, no character restrictions |
| 3 | Bio Text | Always | Always | Always | Max 160 characters |
| 4 | Profile Picture | Always | Always | Always | Downloadable via URL |
| 5 | Banner/Header Image | Always | Always | Always | Downloadable via URL |
| 6 | Followers Count | Always | Always | Always | Shown publicly |
| 7 | Following Count | Always | Always | Always | Shown publicly |
| 8 | Tweet/Post Count | Always | Always | Always | Total count visible |
| 9 | Join Date | Always | Always | Always | Month + Year, always public |
| 10 | Location Field | Always | Always | Always | Free text, user-entered, unverified |
| 11 | Website/External URL | Always | Always | Always | Single link in bio |
| 12 | Verified Badge | Always | Always | Always | Blue = subscription, Gold = organization |
| 13 | Tweet Content | Full access | Blocked | Full access | Public tweets only |
| 14 | Hashtags in Tweets | Extractable | Blocked | Extractable | From tweet text |
| 15 | Tweet Timestamps | Extractable | Blocked | Extractable | ISO format, includes client source |
| 16 | Tweet Location Tags | If tagged | Blocked | If tagged | User must opt in |
| 17 | Mentioned Users | Extractable | Blocked | Extractable | @username in tweet text |
| 18 | Retweets | Extractable | Blocked | Extractable | Distinguish RT vs Quote Tweet |
| 19 | Quote Tweets | Extractable | Blocked | Extractable | Original + added comment |
| 20 | Replies (by user) | Extractable | Blocked | Extractable | Rate limited, needs pagination |
| 21 | Likes (by user) | Hard to scrape | Blocked | Hard to scrape | Not shown on profile by default since 2023 |
| 22 | Media in Tweets | Extractable | Blocked | Extractable | Images/video/GIF attachments |
| 23 | Pinned Tweet | Visible | Blocked | Visible | Top of profile |
| 24 | Lists (created) | Visible if public | Blocked | Visible if public | Named collections of accounts |
| 25 | Lists (member of) | Visible | Blocked | Visible | Shows which public lists include the account |
| 26 | Followers List | Rate limited | Not accessible | Rate limited | API-gated, heavily throttled |
| 27 | Following List | Rate limited | Not accessible | Rate limited | API-gated, heavily throttled |
| 28 | Former Usernames | Not exposed | Not exposed | Not exposed | Only via historical snapshot comparison |
| 29 | Account ID (numeric) | Extractable | Extractable | Extractable | Static, never changes even if handle changes — strong identifier |
| 30 | Tweet Source/Client | Extractable | Blocked | Extractable | "Twitter for iPhone", "Web App", etc. |
| 31 | Circle Tweets | Not accessible | Not accessible | Not accessible | Visible only to Circle members |
| 32 | Spaces (hosted/joined) | Visible if public | Blocked | Visible if public | Audio room participation |
| 33 | Bookmarks | Not accessible | Not accessible | Not accessible | Private to the account owner |
| 34 | Direct Messages | Not accessible | Not accessible | Not accessible | Requires legal process |
| 35 | Analytics (impressions etc.) | Not accessible | Not accessible | Not accessible | Private to account owner |
| 36 | Email/Phone (linked) | Not accessible | Not accessible | Not accessible | Not exposed via profile or API |
| 37 | Login IP History | Not accessible | Not accessible | Not accessible | Requires legal process |
| 38 | Deleted Tweets | Not accessible (live) | Not accessible | Not accessible (live) | Only via third-party archives if captured before deletion |
| 39 | LinkedIn/Other Links | If in bio | If in bio | If in bio | Scrape from bio text |
| 40 | Professional Email | If in bio | If in bio | If in bio | Regex extraction from bio |

---

## 4. Rate Limiting Patterns

**Observed limits (from testing, unauthenticated/guest access):**

| Action | Limit | Time Window | Consequence |
|---|---|---|---|
| Profile page views | ~50–100 | Per hour (per IP) | Login wall triggered |
| Tweet timeline scroll | ~limited posts | Per session without login | Redirect to login prompt |
| Search queries | Very restricted | Per hour | Login wall almost immediately |
| API v2 (authenticated, free tier) | 1 request / 15 min (user lookup) | Per endpoint | 429 error |
| API v2 (authenticated, basic tier) | Varies by endpoint | Per month cap + per 15 min | 429 error, quota exhaustion |

**Recommended delays:**

| Scenario | Delay |
|---|---|
| Between profile requests | 5–10 seconds (random) |
| Between timeline scrolls | 3–6 seconds (random) |
| After rate limit hit | Wait 15 minutes minimum (matches API reset window) |
| After login wall/block | Use authenticated session or wait 1+ hour |

**Rate limit detection signals:**
- HTTP 429 "Too Many Requests"
- Forced redirect to `/i/flow/login`
- Response contains `"Rate limit exceeded"`
- Truncated or empty timeline data
- CAPTCHA/"unusual activity" interstitial

---

## 5. Anti-Scraping Measures

**Twitter/X's defense layers:**

| Layer | What Happens | How to Handle |
|---|---|---|
| 1 — Guest Rate Limit | Very low ceiling for unauthenticated requests | Use authenticated session, add delays |
| 2 — Login Wall | Timeline/search cuts off after a few scrolls | Use logged-in session cookies |
| 3 — API Rate Limit | 429 on API v2 endpoints | Respect per-endpoint reset windows |
| 4 — Challenge/CAPTCHA | "Unusual login activity" or phone verification prompt | Wait, reduce frequency, use verified account |
| 5 — Account Suspension | Scraping account flagged/locked | Use dedicated low-risk account, avoid automation patterns |

**Bypass strategies (priority order):**
1. **Authenticated session** — logged-in access has meaningfully higher limits than guest access
2. **Random delays** — never use fixed intervals, randomize 5–10 seconds
3. **Official API where possible** — more stable than scraping, but has its own quota tiers
4. **Realistic browser fingerprint** — real user-agent, proper headers, avoid headless-detection triggers
5. **Session/cookie reuse** — avoid repeated fresh logins, which increase suspicion

---

## 6. Error Handling — Complete Reference

| Error Type | Meaning | Developer Action |
|---|---|---|
| `UserNotFoundError` | Handle does not exist | Return error: "Profile not found" |
| `AccountSuspendedError` | Account has been suspended by platform | Return `status=suspended`, no further data |
| `ProtectedAccountError` | Account tweets are protected | Return limited profile data, `is_protected=true` |
| `RateLimitExceeded` (429) | Too many requests | Wait for reset window, retry |
| `LoginRequiredError` | Guest limit exhausted | Load authenticated session |
| `ChallengeRequiredError` | CAPTCHA/verification triggered | Notify user, pause scraping |
| `ConnectionError` | Network issue | Retry 3x with exponential backoff |
| `InvalidHandleFormatError` | Handle fails format validation | Validate handle before request |
| `DeactivatedAccountError` | Account deactivated by user | Return `status=deactivated` |

**Error response format (for frontend):**
```json
{
  "error": true,
  "error_type": "RATE_LIMITED",
  "message": "Too many requests. Please wait before retrying.",
  "retry_after_seconds": 900,
  "username": "test_user",
  "timestamp": "2026-07-02T14:30:00Z"
}
```

---

## 7. Indian User Behavior Patterns

**Common patterns observed:**

| Pattern | Example | OSINT Value |
|---|---|---|
| Phone in bio | "DM/Call: 9876543210" | Direct identifier |
| Hindi/Devanagari bio | "जय हिन्द! दिल्ली से हूँ" | Requires UTF-8 handling |
| Hinglish mix | "Delhi se hu, cricket lover" | Stylometric analysis |
| Multiple platform links | "IG: @xyz | YT: xyz Vlogs" | Cross-platform discovery |
| Linktree/Bio.link | "linktr.ee/username" | Single click reveals 4–6 platforms |
| Political/regional affiliation tags | "Proud [state] | [party] Karyakarta" | Affiliation mapping |
| Location in bio | "Mumbai | India" | Geocoding |
| Email in bio | "Business: email@gmail.com" | Direct identifier |
| College/university/employer | "DU'24 | Ex-TCS" | Cross-reference with LinkedIn |
| Pinned tweet as intro | Thread pinned introducing self, work, links | Bio expansion — often richer than the bio field itself |

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
| 1 | Instant | Handle, Display Name, Bio, Profile Pic URL, Verified Status |
| 2 | Instant | Follower Count, Following Count, Tweet Count, Join Date |
| 3 | Fast | Location field, Website/External URL, Account ID |
| 4 | Medium | Last 20–50 Tweets — text + hashtags + mentions |
| 5 | Medium | Tweet Timestamps, Media attachments, Retweet/Quote Tweet flags |
| 6 | Slow | Profile/Banner image download + pHash computation |
| 7 | Optional | Lists membership, Spaces history, pinned tweet thread expansion |

**Parallel processing where possible:**
- Can run in parallel: Step 1 + Step 2 (independent data)
- Can run in parallel: Profile image download + Timeline fetch (different endpoints)
- Must run sequentially: Timeline fetch → hashtag/mention extraction (dependency)

---

## 9. Data Integrity & Validation

**Checks before storing:**

| Data Point | Validation Rule |
|---|---|
| Handle | Must match input (case-insensitive) |
| Display Name | Not empty |
| Follower Count | Must be integer ≥ 0 |
| Following Count | Must be integer ≥ 0 |
| Tweet Count | Must be integer ≥ 0 |
| Account ID | Must be numeric, non-null — use as primary key over handle |
| Profile Pic URL | Must return HTTP 200 |
| Bio | Can be empty string (valid) |
| External URL | If present, must start with `http` |

**Important note:** Always store the numeric **Account ID** alongside the handle. Handles can be changed by the user at any time; the Account ID remains constant and is the reliable link for cross-referencing historical data.

---

## 10. Fallback Sources

**When Twitter/X blocks access:**

| Source | What It Provides | Limitation |
|---|---|---|
| Google Cache | Last indexed version of profile | May be outdated (days/weeks) |
| Wayback Machine | Historical profile and tweet snapshots | Not real-time |
| Nitter instances (where still operational) | Lightweight profile/tweet view | Most public instances are inconsistently available |
| Google Dorks | `site:x.com "handle"` or `site:twitter.com "handle"` | Search result snippets only |

**Fallback order:**
1. Twitter/X direct (primary)
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
- Protected account data requires legal process (court order)
- DM content is never accessible without a court order
- IP/login history data is never accessible without a court order
- Data collected must have an audit trail (Section 65B, Evidence Act)
- All investigations must be logged with timestamp and officer ID

---

## 12. Summary — Developer Quick Reference

| Question | Answer |
|---|---|
| Max requests per hour (guest)? | Very low, ~50–100 profile views before login wall |
| Delay between requests? | Random 5–10 seconds |
| Login needed? | Effectively yes — guest access is heavily restricted |
| Protected account data? | Only handle, name, bio, pic — no tweets |
| Non-existent handle? | Return clear error, no crash |
| Indian phone regex? | `[6-9]\d{9}` after normalization |
| Hindi text handling? | UTF-8, NFC normalization, preserve all characters |
| Strongest unique identifier? | Numeric Account ID, not the handle |
| Handle changes? | Common — always cross-check via Account ID |
| Error format? | JSON with `error_type`, `message`, `retry_after` |
| Audit required? | Yes — log all investigations per IT Act |

---

*End of document*
