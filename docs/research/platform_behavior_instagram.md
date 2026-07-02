Sprint 1 Research Document
Prepared by: [SHUBHAM JHA]
Date: 28 June 2026
Sprint: Sprint 1
Reference: Instagram Data Points Catalog (40 Points)

1. PURPOSE
This document explains Instagram's behavior patterns for OSINT data extraction. It covers URL structure, public vs private visibility, rate limits, anti-scraping measures, error handling, and Indian user-specific patterns. Developers use this to implement robust data fetching without crashes or blocks.


2. INSTAGRAM PROFILE URL STRUCTURE
Standard Format:
https://www.instagram.com/{username}/


Rules:
Username is case-insensitive in URL but stored as lowercase
Maximum 30 characters
Allowed: letters (a-z), numbers (0-9), underscore (_), period (.)
Period cannot be at start or end
Consecutive periods not allowed


Examples:

https://www.instagram.com/lavkumar_ig/     ✅ Valid
https://www.instagram.com/test.user.2024/  ✅ Valid
https://www.instagram.com/.test_user/      ❌ Invalid (leading dot)
https://www.instagram.com/test..user/      ❌ Invalid (consecutive dots)


3. DATA VISIBILITY MATRIX
By Account Type:
Data Point (from Catalog)	Public Account	Private Account	Business Account	Notes
Username (#1)	✅ Always	✅ Always	✅ Always	Primary identifier
Full Name (#2)	✅ Always	✅ Always	✅ Always	Display name, can be anything
Bio Text (#3)	✅ Always	✅ Always	✅ Always	Max 150 characters
Profile Picture (#4)	✅ Always	✅ Always	✅ Always	Downloadable via URL
Followers Count (#5)	✅ Always	✅ Always	✅ Always	Number shown publicly
Following Count (#6)	✅ Always	✅ Always	✅ Always	Number shown publicly
Post Count (#7)	✅ Always	✅ Always	✅ Always	Total posts count visible
External URL (#8)	✅ Always	✅ Always	✅ Always	Single clickable link in bio
Verified Badge (#9)	✅ Always	✅ Always	✅ Always	Blue tick visible
Business Category (#10)	✅ If business	❌ Personal	✅ Always	e.g., "Product/Service"
Account Creation Date (#11)	⚠️ Estimate only	⚠️ Estimate only	⚠️ Estimate only	Not directly exposed; check first post
Posts Content - Captions (#12)	✅ Full access	❌ Blocked	✅ Full access	Public posts only
Post Hashtags (#13)	✅ Extractable	❌ Blocked	✅ Extractable	From caption text
Post Timestamps (#14)	✅ Extractable	❌ Blocked	✅ Extractable	ISO format
Post Location Tags (#15)	✅ If tagged	❌ Blocked	✅ If tagged	User must opt-in
Tagged Users in Posts (#16)	✅ Extractable	❌ Blocked	✅ Extractable	From post metadata
Mentioned Users (#17)	✅ From captions	❌ Blocked	✅ From captions	@username in text
Comments Made (#18)	⚠️ Hard to scrape	❌ Blocked	⚠️ Hard	Rate limited, needs login
Tagged Photos (#19)	⚠️ Privacy dependent	❌ Blocked	⚠️ Privacy dependent	Depends on tag review settings
Profile Picture Hash (#20)	✅ Computable	✅ Computable	✅ Computable	pHash from downloaded image
Linked FB Account (#21)	⚠️ Not always visible	❌ Hidden	⚠️ Sometimes linked	In "Accounts Center"
Story Highlights (#22)	✅ Titles public	✅ Titles public	✅ Titles public	Content inside is public
Reels/IGTV Count (#23)	✅ Visible	✅ Visible	✅ Visible	Tab count on profile
Account Country (#24)	⚠️ Estimate only	⚠️ Estimate only	⚠️ Estimate only	From About section if available
Former Usernames (#25)	✅ If not hidden	✅ If not hidden	✅ If not hidden	About → Former Usernames
Active Ads (#26)	✅ If running	❌ Hidden	✅ If running	About → Active Ads
Account Type (#27)	✅ Visible	✅ Visible	✅ Visible	Personal/Creator/Business
Contact Email (#28)	❌ Personal	❌ Hidden	✅ If provided	Business/Creator only
Contact Phone (#29)	❌ Personal	❌ Hidden	✅ If provided	Business/Creator only
Contact Address (#30)	❌ Personal	❌ Hidden	✅ If provided	Business/Creator only
Pinned Posts (#31)	✅ Visible	❌ Blocked	✅ Visible	Top 3 posts on grid
Collab Posts (#32)	⚠️ Hard	❌ Blocked	⚠️ Hard	Needs post metadata
Story Replies (#33)	❌ Not accessible	❌ Not accessible	❌ Not accessible	Only while story live + login
Followers List (#34)	❌ IMPOSSIBLE	❌ IMPOSSIBLE	❌ IMPOSSIBLE	Rate limited, login required
Following List (#35)	❌ IMPOSSIBLE	❌ IMPOSSIBLE	❌ IMPOSSIBLE	Rate limited, login required
Likes on Others' Posts (#36)	❌ IMPOSSIBLE	❌ IMPOSSIBLE	❌ IMPOSSIBLE	Not publicly available
EXIF Metadata (#37)	❌ IMPOSSIBLE	❌ IMPOSSIBLE	❌ IMPOSSIBLE	Instagram strips EXIF post-2012
DM Content (#38)	❌ IMPOSSIBLE	❌ IMPOSSIBLE	❌ IMPOSSIBLE	Requires court order
LinkedIn Link (#39)	✅ If in bio	✅ If in bio	✅ If in bio	Scrape from bio text
Professional Email (#40)	✅ If in bio	✅ If in bio	✅ If in bio	Regex extraction from bio


4. RATE LIMITING PATTERNS
Observed Limits (from testing):
Action	Limit	Time Window	Consequence
Profile page requests	~200	Per hour	IP blocked for 30 min
Post content fetch	~100	Per hour	Throttled, slower responses
Image download	~500	Per hour	CDN blocks temporarily
Search queries	~50	Per hour	Rate limit error
Login attempts	~5	Per 10 minutes	Account locked temporarily


Recommended Delays:
Between profile requests:    3-7 seconds (random)
Between post fetches:        2-5 seconds (random)
After rate limit hit:        Wait 30 minutes minimum
After IP block:              Switch IP or wait 1 hour

Rate Limit Detection:
HTTP 429 "Too Many Requests"
Response contains "challenge_required"
Redirect to login page
Empty response body
Response time suddenly > 30 seconds


5. ANTI-SCRAPING MEASURES
Instagram's Defense Layers:
Layer	What Happens	How to Handle
Layer 1: Rate Limit	429 errors after ~200 req/hr	Add delays, rotate IPs
Layer 2: Login Wall	Redirects to login page	Use saved session cookies
Layer 3: Challenge Page	CAPTCHA or "suspicious activity"	Wait 24-48 hours, reduce frequency
Layer 4: IP Block	Complete access denied	Use proxy/VPN, wait longer
Layer 5: Account Block	Account flagged	Use different account, appeal


Bypass Strategies (in priority order):
Session Persistence: Save login session file, reuse across runs
Random Delays: Never use fixed delays, always randomize 3-7 seconds
User-Agent Rotation: Use real browser user-agents
Request Headers: Include proper Referer, Accept-Language, etc.
Proxy Rotation: Rotate IPs if doing bulk extraction (LEA authorized only)


6. ERROR HANDLING — Complete Reference
Error Type	Meaning	Developer Action
ProfileNotExistsException	Username does not exist	Return error: "Profile not found"
PrivateProfileNotFollowedException	Account is private	Return limited data, is_private=true
RateLimitExceeded (429)	Too many requests	Wait 30 min, retry
LoginRequiredException	Login wall hit	Load session or prompt for login
ChallengeRequiredException	CAPTCHA triggered	Notify user, wait 24 hours
ConnectionError	Network issue	Retry 3x with exponential backoff
QueryReturnedNotFoundException (404)	Invalid query	Validate username format before request
BadCredentialsException (401)	Login failed	Check credentials, notify user
TwoFactorAuthRequiredException	2FA enabled	Not supported — use session file


Error Response Format (For Frontend):
{
  "error": true,
  "error_type": "RATE_LIMITED",
  "message": "Too many requests. Please wait 30 minutes.",
  "retry_after_seconds": 1800,
  "username": "test_user",
  "timestamp": "2026-06-28T14:30:00Z"
}


7. INDIAN USER BEHAVIOR PATTERNS
Common Patterns Observed:
Pattern	Example	OSINT Value
Phone in Bio	📞 9876543210 / WA: +91 98765 43210	Direct identifier — Rule #2
Hindi/Devanagari Bio	नमस्ते! मैं दिल्ली से हूँ	UTF-8 handling required
Hinglish Mix	Delhi ka photographer hu, travel lover ❤️	Stylometric analysis — Rule #14
Multiple Platform Links	Twitter: @xyz | Snap: xyz_snap | YT: xyz	Cross-platform discovery
Linktree/Bio.link	linktr.ee/username	Single click reveals 4-6 platforms — Rule #16
Business WhatsApp	Business inquiries: WA +91 98XXX	WhatsApp not directly scrapable
Location in Bio	📍 Mumbai | Pune | India	Geocoding — Rule #9
Email in Bio	Collab: email@gmail.com	Direct identifier — Rule #3
College/University	DU'24 | IITian | NMIMS	Education verification — cross-ref LinkedIn


Phone Number Formats Found in Indian Bios:
Original in Bio      → Normalized
📞 9876543210        → 9876543210
+91 98765 43210     → 9876543210
09876543210         → 9876543210
98765-43210         → 9876543210
+91-98765-43210     → 9876543210
Regex for Indian Mobile: [6-9]\d{9} (after stripping +91, 0, spaces, dashes)


8. DATA EXTRACTION — P0 SEQUENCE
Recommended Extraction Order (Fastest to Slowest):
text
Step 1 (Instant):  Username, Full Name, Bio, Profile Pic URL, Verified Status
Step 2 (Instant):  Follower Count, Following Count, Post Count, Account Type
Step 3 (Fast):     External URL, Business Category, Contact Info (if Business)
Step 4 (Medium):   Last 12 Posts Captions + Hashtags
Step 5 (Medium):   Post Timestamps, Location Tags, Tagged Users
Step 6 (Slow):     Profile Picture Download + pHash computation
Step 7 (Optional): Comments, Tagged Photos, Story Highlights


Parallel Processing Where Possible:
✅ Parallel: Step 1 + Step 2 (independent data)
✅ Parallel: Profile pic download + Post fetch (different endpoints)
❌ Sequential: Post fetch then hashtag extraction (dependency)


9. DATA INTEGRITY & VALIDATION
Checks Before Storing:
Data Point	Validation Rule
Username	Must match input (case-insensitive)
Full Name	Not empty, not "Instagram User" (default)
Follower Count	Must be integer ≥ 0
Following Count	Must be integer ≥ 0
Post Count	Must be integer ≥ 0
Profile Pic URL	Must return HTTP 200
Bio	Can be empty string (valid)
External URL	If present, must start with http


10. FALLBACK SOURCES
When Instagram Blocks:
Source	What It Provides	Limitation
Google Cache	Last indexed version of profile	May be outdated (days/weeks)
Wayback Machine	Historical profile snapshots	Not real-time
Social Blade	Follower count history	No bio/posts
Google Dorks	site:instagram.com "username"	Search result snippets only

Fallback Order:
1. Instagram Direct (primary)
2. Google Cache (if primary blocked)
3. Wayback Machine (if Google Cache empty)
4. Google Dorks (last resort — limited data)
11. LEGAL BOUNDARIES — INDIA


Under IT Act 2000:
Section	Relevance
Section 69	Government can intercept/monitor for national security
Section 69B	Monitor traffic for cyber security incidents
Section 72A	Punishment for disclosure of info without consent


Key Rules for Developers:
✅ Public data scraping is legal (publicly accessible information)
❌ Private account data requires legal process (court order)
❌ DM content never accessible without court order
❌ Instagram EXIF data not available (stripped by platform)
✅ Data collected must have audit trail (Section 65B Evidence Act)
✅ All investigations must be logged with timestamp + officer ID


12. SUMMARY — DEVELOPER QUICK REFERENCE

Question	Answer
Max requests per hour?	~200, then 30-min block
Delay between requests?	Random 3-7 seconds
Login needed?	Session file recommended, not required for public
Private account data?	Only username, name, bio, pic — no posts
Non-existent user?	Return clear error, no crash
Indian phone regex?	[6-9]\d{9} after normalization
Hindi text handling?	UTF-8, NFC normalization, preserve all
Business contact info?	Available for Business/Creator accounts only
Profile pic matching?	pHash for exact; Face embedding for filtered
Error format?	JSON with error_type, message, retry_after
Audit required?	Yes — log all investigations per IT Act
END OF DOCUMENT


