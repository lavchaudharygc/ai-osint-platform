Document: "Username OSINT Investigation Methodology v1.0"

SECTION 1: Trigger Points
- When investigator has only a username
- When investigator has username + platform
- When username is found during other investigation
- Priority levels for each trigger

SECTION 2: Data Collection Sequence (STEP-BY-STEP)
Step 1: Profile Data Extraction
  ├── Instagram: username, full_name, bio, profile_pic, follower_count, following_count, post_count, account_age, business_category
  ├── Twitter: handle, display_name, bio, location, join_date, tweet_count
  ├── Telegram: username, display_name, bio, join_date
  └── LinkedIn: name, headline, location, industry

Step 2: Content Analysis
  ├── Last 12 posts from Instagram
  ├── Last 50 tweets
  ├── Tagged photos count
  └── Commonly used hashtags (top 10)

Step 3: Relationship Mapping
  ├── Who tags this user
  ├── Who this user tags
  ├── Common commenters
  └── Mutual followers patterns

Step 4: Cross-Platform Discovery
  ├── Username pattern matching (exact, leet speak, common variations)
  ├── Profile picture reverse search
  ├── Bio text similarity matching
  └── Connected accounts (Linktree, other social links in bio)

SECTION 3: Correlation Rules (Weighted Scoring)
Rule 1: Exact username match = 30 points
Rule 2: Username pattern match (e.g., lav_insta → lav_twitter) = 20 points
Rule 3: Same profile picture = 25 points
Rule 4: Bio contains same phone/email = 20 points
Rule 5: Bio keyword similarity > 80% = 15 points
Rule 6: Same location mentioned = 10 points
Rule 7: Cross-tagging same accounts = 15 points
Rule 8: Same writing style (AI detected) = 10 points

CONFIDENCE SCORING:
90-100: Definitive match (proceed with high confidence)
70-89: Probable match (verify with additional sources)
50-69: Possible match (flag for manual review)
<50: Insufficient evidence (discard or investigate further)

SECTION 4: Indian Platform Specifics
- Koo: Username patterns, API status
- ShareChat: Mobile-first, region-locked content
- Moj: Video-focused, username to phone correlation
- Josh: Similar to Moj, regional language usernames
- Local platforms: Matrimonial sites, classifieds (OLX, Quikr)