# Telegram Platform Behavior — OSINT Data Extraction Reference

**Prepared by:** Shubham Jha
**Date:** 30 june 2026
**Sprint:** Sprint 1
**Reference:** Telegram Data Points Catalog

---

## 1. Purpose

This document describes Telegram's platform behavior relevant to OSINT data extraction. It covers username/ID structure, public vs. private visibility, rate limits, anti-scraping measures, error handling, and Indian user-specific patterns. It is intended for developers implementing robust data-fetching logic without crashes or blocks.

Telegram differs structurally from Instagram/Twitter: much of it is not web-crawlable, and legitimate data access largely depends on the Telegram API (MTProto via Telethon/Pyrogram) or the Bot API, rather than HTML scraping.

---

## 2. Telegram Username/Profile Structure

**Standard formats:**
```
https://t.me/{username}          — public user or public channel/group
https://t.me/+{invite_hash}      — private group/channel invite link
tg://resolve?domain={username}   — deep link format
```

**Rules:**
- Username is optional — many users have no public username at all
- Minimum 5 characters, maximum 32 characters
- Allowed characters: letters (a-z, A-Z), numbers (0-9), underscore (_)
- Must start with a letter
- Case-insensitive for resolution, but display case is preserved
- A numeric internal **User ID** always exists regardless of whether a username is set — this is the true persistent identifier

**Examples:**

| URL | Valid |
|---|---|
| `https://t.me/shubham_osint` | Yes |
| `https://t.me/ab12` | No — below 5-character minimum |
| `https://t.me/1username` | No — cannot start with a number |
| `https://t.me/+AbCdEf12345` | Yes — private invite link format |

---

## 3. Data Visibility Matrix

| # | Data Point | Public Username Set | No Public Username | Private Group/Channel Member | Notes |
|---|---|---|---|---|---|
| 1 | Username | Always | Not applicable | Always (if set) | Optional field, not all users have one |
| 2 | User ID (numeric) | Always | Always | Always | True persistent identifier |
| 3 | First/Last Name | Always | Always | Always | Self-set, unverified, can be anything |
| 4 | Profile Photo | If public | If public | If public | Depends on user's privacy setting |
| 5 | Bio/About Text | If public | If public | If public | Max 70 characters |
| 6 | Phone Number | Hidden by default | Hidden by default | Hidden by default | Only visible if user explicitly allows, or if in mutual contacts |
| 7 | "Last Seen" Status | Depends on privacy setting | Depends on privacy setting | Depends on privacy setting | User-configurable: Everyone/Contacts/Nobody |
| 8 | Common Groups | Visible to contacts | Visible to contacts | Visible to members | Shows shared group membership |
| 9 | Channel/Group Membership Count | Not exposed | Not exposed | Not exposed | Never publicly visible |
| 10 | Public Channel Subscriber Count | Always | Not applicable | Not applicable | Visible on public channels |
| 11 | Public Channel Post History | Always | Not applicable | Not applicable | Fully scrapable via API or t.me preview |
| 12 | Public Group Message History | Depends on group settings | Not applicable | If member | Some groups have history hidden for new members |
| 13 | Message Timestamps | Extractable | Extractable | Extractable (if member) | Server timestamp, reliable |
| 14 | Forwarded Message Origin | Extractable (if not hidden by sender) | Extractable | Extractable | Users can disable forward attribution |
| 15 | Media in Messages | Extractable | Extractable | Extractable (if member) | Photos, videos, documents, voice notes |
| 16 | Media EXIF/Metadata | Stripped | Stripped | Stripped | Telegram strips metadata on upload |
| 17 | Pinned Messages | Visible | Visible | Visible (if member) | Channel/group level |
| 18 | Admin List (of group/channel) | Visible | Visible | Visible (if member) | Unless hidden by owner |
| 19 | Bot Interactions | Not accessible | Not accessible | Not accessible | Private to user and bot |
| 20 | Read Receipts/Online Status | Depends on privacy setting | Depends on privacy setting | Depends on privacy setting | Often disabled by privacy-conscious users |
| 21 | Linked Discussion Group (of a channel) | Visible | Not applicable | Not applicable | Shown on channel info page |
| 22 | Story Posts | If public | If public | If public | Similar to Instagram Stories, 24-hour default |
| 23 | Username History | Not exposed | Not applicable | Not exposed | Old usernames become available for others to claim |
| 24 | Verified Badge | Visible if verified | Visible if verified | Visible if verified | Rare, platform-granted |
| 25 | Premium Badge | Visible | Visible | Visible | Telegram Premium subscription indicator |
| 26 | Secret Chats | Not accessible | Not accessible | Not accessible | End-to-end encrypted, device-local only, no cloud trace |
| 27 | Self-Destructing Messages | Not accessible | Not accessible | Not accessible | Deleted after viewing/timer |
| 28 | Deleted Messages | Not accessible (live) | Not accessible | Not accessible | Only if captured via bot/log before deletion |
| 29 | Group Member List | Visible if public group | Not applicable | Visible if member | Large groups may cap visible list size |
| 30 | Channel Member List | Not accessible | Not applicable | Not accessible | Channels never expose subscriber lists, only counts |
| 31 | Location Sharing | Not accessible | Not accessible | Not accessible | Live location, private and temporary |
| 32 | Contact Sync Data | Not accessible | Not accessible | Not accessible | Private to the account |
| 33 | IP Address | Not accessible | Not accessible | Not accessible | Requires legal process |
| 34 | Two-Step Verification Email | Not accessible | Not accessible | Not accessible | Requires legal process |
| 35 | Call Logs | Not accessible | Not accessible | Not accessible | Requires legal process |
| 36 | Bot-Created Channels/Groups Ownership | Extractable via API | Extractable via API | Extractable via API | If bot is admin/member |
| 37 | Linktree/External Links in Bio | If public | If public | If public | Scrape from bio text |
| 38 | Email in Bio | If public | If public | If public | Regex extraction from bio |
| 39 | QR Code/t.me Link Sharing | Always | Always | Always | Common in Indian channel promotion |
| 40 | Channel Description/About | Always | Not applicable | Not applicable | Full text visible on public channels |

---

## 4. Rate Limiting Patterns

**Observed limits (from testing, MTProto API — Telethon/Pyrogram):**

| Action | Limit | Time Window | Consequence |
|---|---|---|---|
| `GetFullUser` / profile lookups | ~200 | Per hour (per session) | `FloodWaitError` |
| Channel/group message history fetch | ~3000 messages | Per request batch (paginated) | Throttled between pages |
| Joining channels/groups | ~20–50 | Per day (new/low-trust accounts) | Temporary join restriction |
| Search queries | Moderate | Per hour | `FloodWaitError` |
| Contact resolution (`ResolveUsername`) | ~200 | Per hour | `FloodWaitError` |
| Bot API calls | 30 messages/second (global) | Continuous | 429 with `retry_after` |

**Recommended delays:**

| Scenario | Delay |
|---|---|
| Between profile/username lookups | 2–5 seconds (random) |
| Between message history page fetches | 1–3 seconds (random) |
| After `FloodWaitError` | Respect the exact wait time returned by the API — do not retry early |
| New account joining channels | Space out joins over hours/days, not in bulk |

**Rate limit detection signals:**
- `FloodWaitError` with a specific `seconds` value (MTProto)
- HTTP 429 with `retry_after` field (Bot API)
- `PEER_FLOOD` error — account temporarily restricted from contacting new peers
- Sudden inability to join new public channels/groups

---

## 5. Anti-Scraping Measures

**Telegram's defense layers:**

| Layer | What Happens | How to Handle |
|---|---|---|
| 1 — Flood Wait | `FloodWaitError` after exceeding action-specific thresholds | Respect returned wait time exactly, add delays |
| 2 — Peer Flood | Restriction on contacting/joining new peers | Reduce join/message rate, use aged accounts |
| 3 — Spam Block | Account flagged, restricted from most actions | Avoid mass automation patterns, use official Bot API where possible |
| 4 — Session Termination | Session revoked, re-authentication required | Store session strings securely, avoid concurrent logins from many IPs |
| 5 — Account Ban | Full account ban (rare, severe abuse cases) | Never automate at volumes resembling spam/bot networks |

**Bypass strategies (priority order):**
1. **Use official API (MTProto or Bot API)** — Telegram has no meaningful public web scraping surface for private data; the API is the primary legitimate route
2. **Aged, verified accounts** — new accounts hit flood limits much faster
3. **Respect FloodWaitError precisely** — retrying before the wait expires escalates restrictions
4. **Bot API for public channels** — often more stable and higher-limit than a user session for public channel monitoring
5. **Avoid bulk joining** — space out group/channel joins to avoid PEER_FLOOD

---

## 6. Error Handling — Complete Reference

| Error Type | Meaning | Developer Action |
|---|---|---|
| `UsernameNotOccupiedError` | Username does not exist | Return error: "Profile not found" |
| `UsernameInvalidError` | Username fails format validation | Validate format before request |
| `FloodWaitError` | Too many requests, includes wait time | Wait exact returned duration, retry after |
| `PeerFloodError` | Too many new contacts/joins in short time | Pause all join/message actions, wait hours |
| `ChatAdminRequiredError` | Action needs admin rights in a group/channel | Skip action, log as restricted |
| `ChannelPrivateError` | Channel/group is private and not joined | Return `is_private=true`, no content access |
| `AuthKeyUnregisteredError` | Session invalid/expired | Re-authenticate, refresh session string |
| `PhoneNumberBannedError` | Account phone number banned by Telegram | Do not retry with same number, log incident |
| `SlowModeWaitError` | Group has slow mode enabled | Wait specified duration before next message action |

**Error response format (for frontend):**
```json
{
  "error": true,
  "error_type": "FLOOD_WAIT",
  "message": "Too many requests. Please wait before retrying.",
  "retry_after_seconds": 300,
  "identifier": "username_or_id",
  "timestamp": "2026-07-02T14:30:00Z"
}
```

---

## 7. Indian User Behavior Patterns

**Common patterns observed:**

| Pattern | Example | OSINT Value |
|---|---|---|
| Phone in bio | "Contact: 9876543210" | Direct identifier |
| Hindi/Devanagari bio | "नमस्ते! यह मेरा चैनल है" | Requires UTF-8 handling |
| Hinglish mix | "Delhi ka channel hai bhai, join karlo" | Stylometric analysis |
| Channel cross-promotion | "IG: @xyz | YT: xyz Vlogs | WA Group link below" | Cross-platform discovery |
| Bulk invite link sharing | "Join: t.me/joinchat/xxxx" | Common for trading tips, exam groups, leak channels |
| Regional/community channel naming | "[City] Jobs Updates", "[State] Govt Exam Group" | Community and location inference |
| Business WhatsApp redirect | "For orders WA +91 98XXX" | Cross-platform contact bridge |
| Location in bio | "Mumbai | India" | Geocoding |
| Email in bio | "Business: email@gmail.com" | Direct identifier |
| Reused usernames across platforms | Same handle as Instagram/Twitter | Direct cross-platform correlation |

**Phone number formats found in Indian bios:**

| Original in Bio | Normalized |
|---|---|
| "Contact: 9876543210" | 9876543210 |
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
| 1 | Instant | Username (if set), User ID, First/Last Name, Bio |
| 2 | Instant | Profile Photo, Verified/Premium Badge, Last Seen status (if visible) |
| 3 | Fast | Common Groups (if any), Public Channel description/subscriber count |
| 4 | Medium | Public channel/group message history (paginated) |
| 5 | Medium | Media attachments, forwarded message origins |
| 6 | Slow | Profile/media download + pHash computation |
| 7 | Optional | Admin list, pinned messages, linked discussion group |

**Parallel processing where possible:**
- Can run in parallel: Step 1 + Step 2 (independent data)
- Can run in parallel: Profile photo download + message history fetch (different endpoints)
- Must run sequentially: Message history fetch → media/forward-origin extraction (dependency)

---

## 9. Data Integrity & Validation

**Checks before storing:**

| Data Point | Validation Rule |
|---|---|
| User ID | Must be numeric, non-null — always use as primary key over username |
| Username | If present, must match Telegram format rules; can be absent entirely |
| First Name | Not empty (Telegram requires at least a first name) |
| Bio | Can be empty string (valid) |
| Profile Photo URL | Must resolve via API call, not always a direct HTTP URL |
| Subscriber/Member Count | Must be integer ≥ 0 |
| External URL | If present, must start with `http` or `t.me` |

**Important note:** Always store the numeric **User ID** alongside the username. Usernames are optional and can be changed or removed entirely; the User ID is the only reliable constant for cross-referencing historical data.

---

## 10. Fallback Sources

**When direct access is restricted:**

| Source | What It Provides | Limitation |
|---|---|---|
| Google Cache | Last indexed t.me preview page | May be outdated (days/weeks) |
| Wayback Machine | Historical t.me channel/group preview snapshots | Not real-time, and only covers public preview pages |
| Telegram channel aggregator sites (e.g. TGStat) | Channel stats, growth history, category | Third-party, not officially affiliated, data lag possible |
| Google Dorks | `site:t.me "channel_name"` | Search result snippets only |

**Fallback order:**
1. Telegram API direct — MTProto or Bot API (primary)
2. t.me public preview page (for channels/groups with public username, no login required)
3. Google Cache / Wayback Machine (if primary blocked)
4. Third-party aggregators or Google Dorks (last resort — limited, unverified data)

---

## 11. Legal Boundaries — India

**Under IT Act 2000:**

| Section | Relevance |
|---|---|
| Section 69 | Government can intercept/monitor for national security |
| Section 69B | Monitor traffic for cyber security incidents |
| Section 72A | Punishment for disclosure of information without consent |

**Key rules for developers:**
- Public channel/group data scraping is legal (publicly accessible information)
- Private group/channel data requires legal process or legitimate membership
- Secret Chats are end-to-end encrypted and not obtainable through any standard legal process on Telegram's servers
- Phone number, IP address, and call logs require legal process (MLAT/court order — Telegram publishes limited data retention and complies only with valid legal requests)
- Data collected must have an audit trail (Section 65B, Evidence Act)
- All investigations must be logged with timestamp and officer ID

---

## 12. Summary — Developer Quick Reference

| Question | Answer |
|---|---|
| Max requests per hour? | ~200 profile/username lookups before FloodWait |
| Delay between requests? | Random 2–5 seconds |
| Login needed? | Yes for full API access; public channels have a limited no-login preview via t.me |
| Private group/channel data? | Only accessible if a member; otherwise blocked entirely |
| Non-existent username? | Return clear error, no crash |
| Indian phone regex? | `[6-9]\d{9}` after normalization |
| Hindi text handling? | UTF-8, NFC normalization, preserve all characters |
| Strongest unique identifier? | Numeric User ID, not the username |
| Username changes/removal? | Common — always cross-check via User ID |
| Error format? | JSON with `error_type`, `message`, `retry_after` |
| Audit required? | Yes — log all investigations per IT Act |

---

*End of document*
