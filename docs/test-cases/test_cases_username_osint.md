OSINT Investigation Tool - Test Cases
Cross-Platform Correlation Testing (Updated: Instagram, Twitter, Facebook, LinkedIn, Telegram, GitHub, Reddit)

Prepared by: SHUBHAM JHA
Sprint: Sprint 1 (Updated)

Reference Documents:
- Instagram Data Points Catalog (40 points)
- Twitter Data Points Catalog (33 points)
- Facebook Data Points Catalog (31 points)
- LinkedIn Data Points Catalog (30 points)
- Telegram Data Points Catalog (28 points)
- GitHub Data Points Catalog (26 points)
- Reddit Data Points Catalog (23 points)
- Cross-Platform Correlation Rules (29 rules, Weights 0-30)

Scoring Thresholds (Correlation Rule #30 - Aggregate Confidence Score):
0-29 = LOW - Flag for review
30-54 = MEDIUM - Probable same person
55-79 = HIGH - Likely same person
80+ = VERY HIGH - Near-certain

----------------------------------------

Test Case Summary

TC-01 - Exact Username - 3 Platforms - P0 - IG + TW + TG - Expected Score 80+ - VERY HIGH
TC-02 - Same Phone Number in Bio - P0 - IG + TW + FB - Expected Score 80+ - VERY HIGH
TC-03 - Same Email Address in Bio - P0 - IG + TW - Expected Score 80+ - VERY HIGH
TC-04 - Same Website/URL in Bio - P0 - IG + GitHub - Expected Score 55-79 - HIGH
TC-05 - Same Profile Picture - pHash - P0 - IG + TW + TG - Expected Score 55-79 - HIGH
TC-06 - Different Person - Similar Username - P0 - IG + TW - Expected Score 0-29 - LOW
TC-07 - Instagram Business Account - Contact Info - P0 - IG - N/A - Data Extraction
TC-08 - Twitter Profile - All P0 Points - P0 - TW - N/A - Data Extraction
TC-09 - Facebook Work & Education Cross-Ref - P0 - FB - N/A - Data Extraction
TC-10 - LinkedIn Professional Identity - Full P0 - P0 - LI - N/A - Data Extraction
TC-11 - LinkedIn Cross-Reference with Social Platforms - P0 - LI + IG + TW - Expected Score 55-79 - HIGH
TC-12 - GitHub Commit Email Cross-Reference - P0 - GitHub + IG - Expected Score 55-79 - HIGH
TC-13 - GitHub Bio Social Links - P0 - GitHub - N/A - Data Extraction
TC-14 - Reddit Social Links in Profile - P0 - Reddit + TW - Expected Score 55-79 - HIGH
TC-15 - Reddit Self-Disclosed Info - P1 - Reddit - N/A - Data Extraction
TC-16 - Telegram Channel - Posts & Ownership - P1 - TG - N/A - Data Extraction
TC-17 - Telegram Phone Sync Discovery - P1 - TG - Expected Score 30-54 - MEDIUM
TC-18 - Private Instagram Account - P1 - IG - N/A - Limited Data
TC-19 - Non-Existent Username - P1 - All - N/A - Error Handling
TC-20 - Bio Link Graph Traversal - Linktree - P1 - IG - Expected Score 55-79 - HIGH
TC-21 - Cross-Tagging & Mutual Mentions - P2 - IG - Expected Score 30-54 - MEDIUM
TC-22 - Post Timing Pattern Correlation - P2 - TW + GitHub - Expected Score 30-54 - MEDIUM
TC-23 - GitHub/Reddit Writing Style Match - P2 - GitHub + Reddit - Expected Score 0-29 - LOW (alone)
TC-24 - 5-Platform Maximum Correlation - P0 - IG+TW+FB+LI+TG - Expected Score 80+ - VERY HIGH
TC-25 - Database Lookup - P0 - Local DB - N/A - Data Extraction
TC-26 - Google Dorking - P1 - Unique username - N/A - Data Extraction
TC-27 - Multi-Platform (IG + Twitter + GitHub) - P0 - IG+TW+GitHub - Expected Score 80+ - VERY HIGH
TC-28 - Adult Site Detection (Risk Flag) - P1 - Adult platform via dorking - N/A - Risk Flag

----------------------------------------

P0 - CRITICAL (Must Pass)

----------------------------------------

TC-01: Exact Username Match - 3 Platforms

Priority: P0
Correlation Rule Tested: Rule #1 (Exact Username Match, Weight 30)

Input:
Instagram username: same_user_123
Twitter username: same_user_123
Telegram username: same_user_123

Expected Results:
Username found and confirmed on all 3 platforms. Case-insensitive match detected. @prefix normalized before comparison. Rule #1 triggered: Weight +30. Tier: VERY HIGH (80+) when combined with at least one other corroborating signal (e.g. matching profile pic).

Pass Criteria: 3-platform exact match correctly contributes +30 and reaches VERY HIGH when stacked with a second signal.

----------------------------------------

TC-02: Same Phone Number in Bio - Indian Formats

Priority: P0
Correlation Rule Tested: Rule #2 (Same Phone Number in Bio, Weight 30)

Input:
Instagram phone in bio: Call: +91 98765 43210
Twitter phone in bio: WA: 09876543210
Facebook phone in bio: 98765-43210

Expected Results:
Regex [6-9]\d{9} extracts all 3 numbers. +91 prefix stripped, leading 0 removed. All normalized to 9876543210. Exact match detected across all 3 platforms. Rule #2 triggered: Weight +30. Tier: VERY HIGH (80+) on its own since weight 30 plus username partial match typically pushes past 55-79 even before other signals.

Pass Criteria: All Indian phone formats normalized identically and matched; weight 30 applied correctly (updated from 25).

----------------------------------------

TC-03: Same Email Address in Bio

Priority: P0
Correlation Rule Tested: Rule #3 (Same Email Address in Bio, Weight 30)

Input:
Instagram bio content: contact@realbusiness.in
Twitter bio content: contact@realbusiness.in

Expected Results:
Email extracted from both bios. Normalized to lowercase. Domain checked against burner-email list (mailnull, guerrilla, etc.) - none flagged here. Rule #3 triggered: Weight +30. Tier: VERY HIGH (80+) when combined with one more signal (e.g. exact username).

Pass Criteria: Email match correctly adds +30 (updated from 25) to aggregate score.

----------------------------------------

TC-04: Same Website / URL in Bio

Priority: P0
Correlation Rule Tested: Rule #13 (Same Website/URL in Bio, Weight 30)

Input:
Instagram bio/profile URL: johndoe.dev
GitHub website field: johndoe.dev

Expected Results:
Domain extracted and normalized from both platforms. Exact domain match detected. Rule #13 triggered: Weight +30. Tier: HIGH (55-79) on its own; VERY HIGH if combined with username or bio match.

Pass Criteria: Identical personal website across platforms correctly scores +30 (updated from 18).

----------------------------------------

TC-05: Same Profile Picture - pHash Match

Priority: P0
Correlation Rule Tested: Rule #4 (Same Profile Picture, Weight 25)

Input:
Instagram image: original_photo.jpg
Twitter image: Same photo cropped 10%
Telegram image: Same photo with filter

Expected Results:
pHash (8x8 DCT) computed for all 3 images. Cropped version: Hamming distance <=10 -> match via Rule #4. Heavily filtered version: pHash may fail -> falls back to Rule #6 (Face Embedding, Weight 20). At least one rule triggers per platform pair.

Pass Criteria: pHash identifies same image after light edits; face embedding catches heavier edits.

----------------------------------------

TC-06: Different Person - Similar Username (False Positive Check)

Priority: P0
Correlation Rule Tested: Aggregate scoring - must NOT produce false positive

Input:
Instagram username: rahul_sharma_x, Name: Rahul Sharma, Location: Delhi
Twitter username: rahul_sharma, Name: Rahul Sharma, Location: Bangalore

Expected Results:
Rule #5 triggers: Username Pattern Match (+20). Same display name is common (no dedicated identity weight for name alone). Different location -> Rule #9 (Same Location String) does NOT trigger. Different profile picture -> Rule #4 does NOT trigger. Final aggregate score: <=29. Tier: LOW (0-29). System output: "UNLIKELY SAME PERSON - insufficient corroborating signals."

Critical: Tool must NOT report HIGH/VERY HIGH confidence here.

Pass Criteria: Score stays in LOW tier despite username similarity, due to mismatched location & photo.

----------------------------------------

TC-07: Instagram Business Account - Contact Info

Priority: P0
Data Points Tested: Instagram #27, #28, #29, #30 (Account Type, Contact Email, Contact Phone, Contact Address)

Input: Instagram Business account: test_business_india

Expected Data Points:
#27 Account Type - Business
#28 Contact Email - Extracted
#29 Contact Phone - Extracted
#30 Contact Address - Extracted (if present)

Pass Criteria: Contact info correctly extracted from a business-category Instagram account.

----------------------------------------

TC-08: Twitter Profile - All P0 Points

Priority: P0
Data Points Tested: Twitter P0 set (#1-4, 7, 9-11, 14-16, 26, 32)

Input: Twitter: test_user_twitter

Expected P0 Data Points:
#1 Handle, #2 Display Name, #3 Bio Text, #4 Profile Picture, #7 Website/Link in Bio, #9 Followers Count, #10 Following Count, #11 Tweet Count, #14 Tweet Content, #15 Tweet Media, #16 Hashtags Used, #26 Protected/Private Flag, #32 LinkedIn Link in Bio - all must work.

Pass Criteria: 11/13 P0 points extracted minimum.

----------------------------------------

TC-09: Facebook Work & Education Cross-Reference

Priority: P0
Data Points Tested: Facebook #5, #30, #31 (Work and Education History, Work & Education cross-ref LinkedIn, Professional Title Tag)

Input: Facebook profile: test_fb_profile

Expected Results:
Work and Education History section scraped. Professional title/employer tag extracted. System flags discrepancy if Facebook work history does NOT match LinkedIn data for the same subject (when LinkedIn profile already correlated). Rule #30 (Facebook "Work & Education cross-ref LinkedIn") data point populated.

Pass Criteria: Facebook employer data extracted and compared against LinkedIn when available.

----------------------------------------

TC-10: LinkedIn Professional Identity - Full P0 Set

Priority: P0
Data Points Tested: LinkedIn P0 set (#1, 2, 3, 4, 5, 6, 7, 13, 14, 24)

Input: LinkedIn: linkedin_pro_test

Expected P0 Data Points:
#1 Profile URL/Vanity URL, #2 Full Name, #3 Profile Picture, #4 Headline/Title, #5 About/Summary, #6 Current Company & Role, #7 Work History (Past Employers), #13 Contact Info (Email/Phone, if 1st-degree connection), #14 Website/Portfolio Link, #24 Profile Picture Hash - all must work.

Pass Criteria: 9/10 P0 points minimum (Contact Info may be restricted by connection degree).

----------------------------------------

TC-11: LinkedIn Cross-Reference with Social Platforms

Priority: P0
Correlation Rule Tested: Rule #24 (LinkedIn Profile Cross-Reference, Weight 22)

Input:
LinkedIn: Full Name "Priya Verma", Company "TechCorp India", Profile Pic A
Instagram: Bio mentions "TechCorp India", Profile Pic A (same image)
Twitter: LinkedIn link in bio pointing to same LinkedIn URL

Expected Results:
LinkedIn name + employer extracted. Instagram bio mentions same employer. Same profile picture detected via pHash. Twitter bio contains direct LinkedIn URL -> direct link bonus. Rule #24 triggered: Weight +22. Combined with username/photo signals -> Tier: HIGH (55-79).

Pass Criteria: LinkedIn employer + photo match across 2 other platforms correctly scores HIGH tier.

----------------------------------------

TC-12: GitHub Commit Email Cross-Reference

Priority: P0
Correlation Rule Tested: Rule #25 (GitHub Username/Bio Email Cross-Reference, Weight 28)

Input:
GitHub commit email: dev.kumar@gmail.com
Instagram bio email: dev.kumar@gmail.com

Expected Results:
GitHub commit history scanned for email metadata (even if profile email is hidden). Email extracted, normalized to lowercase. Exact match against Instagram bio email. Rule #25 triggered: Weight +28. Tier: HIGH (55-79) on its own; VERY HIGH if username also matches.

Pass Criteria: Commit-leaked email correctly correlates with bio email on another platform.

----------------------------------------

TC-13: GitHub Bio Social Links

Priority: P0
Correlation Rule Tested: Rule #26 (GitHub Bio Social Links, Weight 26)
Data Points Tested: GitHub #6, #7, #8 (Website/Blog Link, Twitter Handle, Company Field)

Input: GitHub profile: dev_test_user with Twitter field populated and Website set to devtestuser.com

Expected Results:
Twitter handle field read directly from GitHub profile metadata (not scraped from bio text). Website link extracted. Company/organization field extracted. Direct link to Twitter account established. Rule #26 triggered: Weight +26.

Pass Criteria: GitHub's dedicated profile fields (not just bio text) are correctly parsed for social links.

----------------------------------------

TC-14: Reddit Social Links in Profile

Priority: P0
Correlation Rule Tested: Rule #28 (Reddit Social Links in Profile, Weight 26)

Input:
Reddit profile social links: Twitter handle @same_user_123
Twitter handle: same_user_123

Expected Results:
Reddit's profile social-link field (not comment text) parsed. Linked Twitter handle extracted. Exact match against Twitter input. Rule #28 triggered: Weight +26. Tier: HIGH (55-79).

Pass Criteria: Reddit native social-link field correctly correlates with linked platform.

----------------------------------------

P1 - HIGH (Should Pass)

----------------------------------------

TC-15: Reddit Self-Disclosed Info Cross-Reference

Priority: P1
Correlation Rule Tested: Rule #27 (Reddit Self-Disclosed Info Cross-Reference, Weight 20)
Data Points Tested: Reddit #11, #12 (Self-Disclosed Location, Self-Disclosed Age/Job/Personal Info)

Input: Reddit: night_owl_redditor - comment in r/AskIndia: "I'm a 27F software engineer based in Pune"

Expected Results:
NLP extracts: age=27, gender=F, profession="software engineer", location="Pune". Cross-checked against Instagram/LinkedIn bio for matching profession/location. Rule #27 triggered if 2 or more of these attributes match another platform: Weight +20.

Pass Criteria: Self-disclosed personal details correctly parsed and cross-referenced.

----------------------------------------

TC-16: Telegram Channel - Posts & Ownership

Priority: P1
Data Points Tested: Telegram #10, #11, #12, #13 (Channel Ownership, Description & Pinned Message, Member Count, Public Channel Posts)

Input: Telegram public channel: public_channel_test

Expected Data Points:
#10 Channel Ownership detected, #11 Description + Pinned Message extracted, #12 Member Count, #13 Public Posts scraped.

Pass Criteria: Channel metadata and post content correctly extracted.

----------------------------------------

TC-17: Telegram Phone Sync Discovery

Priority: P1
Correlation Rule Tested: Rule #18 (Phone-Linked Account Discovery, Weight 23)

Input: Phone: +91-9876543210 (added to a registered test SIM's contacts)

Expected Results:
If target has contact sync ON -> Telegram handle revealed. Display name revealed. Legal note surfaced: requires authorization under IT Act. Rule #18 triggered: Weight +23. Tier: MEDIUM (30-54) on its own.

Pass Criteria: Method works and legal caveat is clearly documented in output.

----------------------------------------

TC-18: Private Instagram Account

Priority: P1

Input: Instagram: private_user_lab

Expected Behavior:
Account privacy status detected. Public-only data returned: Username, Display Name, Profile Picture, Bio (if visible). Posts: NOT accessible, no attempt to bypass. Message: "Private Account - Limited Data Available." No crash, no infinite retry loop. Cross-platform search continues using only the available public data points.

Pass Criteria: Graceful degradation with no crash and accurate "private" labeling.

----------------------------------------

TC-19: Non-Existent Username

Priority: P1

Input: xyz_nonexist_99999 (checked across all 7 platforms)

Expected Behavior:
Each platform independently returns "Profile not found." Response time under 5 seconds per platform. No crash. Aggregate report shows "0/7 platforms found" with suggestion: "Check spelling or try variant spellings."

Pass Criteria: Clear, consistent error handling across all integrated platforms.

----------------------------------------

TC-20: Bio Link Graph Traversal - Linktree

Priority: P1
Correlation Rule Tested: Rule #16 (Linktree/Bio Link, Weight 20), Rule #17 (Bio Link Graph, Weight 22)

Input: Instagram bio contains: linktr.ee/creator_hub

Expected Results:
Bio URL extracted and fetched. All outbound links on the Linktree page parsed. Twitter, YouTube, GitHub handles identified from the link list. Rule #16 triggered: Weight +20. Rule #17: full connected cluster built from traversal (graph node per discovered platform).

Pass Criteria: Single bio link correctly reveals 3+ other platform handles.

----------------------------------------

P2 - MEDIUM (Nice to Pass)

----------------------------------------

TC-21: Cross-Tagging & Mutual Mentions

Priority: P2
Correlation Rule Tested: Rule #7 (Cross-Tagging & Mutual Mentions, Weight 20)

Input: Instagram: network_node_a - has recurring @mentions matching a known Twitter account in the investigation

Expected Results:
@mentions extracted from both platforms. Recurring tag pattern identified (same handle tagged/mentioning back repeatedly). Adjacency list built. Rule #7 triggered when nodes appear on 2 or more platforms: Weight +20.

Pass Criteria: Recurring cross-platform tagging pattern correctly detected.

----------------------------------------

TC-22: Post Timing Pattern Correlation

Priority: P2
Correlation Rule Tested: Rule #11 (Matching Post Timing Patterns, Weight 12)

Input: Twitter night_owl_tweets (50 recent tweets) + GitHub night_owl_dev (50 recent commit timestamps)

Expected Results:
Timestamps extracted from both platforms. Converted to IST. Hourly activity histograms built for each. Pearson correlation computed between the two histograms. Rule #11 triggered if correlation >= 0.70: Weight +12.

Pass Criteria: Activity-hour correlation between Twitter and GitHub correctly computed and scored.

----------------------------------------

TC-23: GitHub/Reddit Writing Style Match (Weak Signal Check)

Priority: P2
Correlation Rule Tested: Rule #29 (GitHub/Reddit Writing Style Match, Weight 12)

Input: GitHub issue comments + Reddit comment history, same writing style (sentence length, vocabulary, Hinglish ratio) but no other matching signal

Expected Results:
Stylometric vectors computed for both comment sets. Cosine similarity calculated. Rule #29 triggers in isolation: Weight +12 only. Aggregate score with ONLY this signal: <=29. Tier: LOW - system must NOT escalate to MEDIUM/HIGH on writing style alone.

Critical: Writing style alone must never push the tier above LOW.

Pass Criteria: Stylometric-only match stays capped at LOW tier, confirming it is correctly treated as a weak/supporting signal.

----------------------------------------

TC-24: 5-Platform Maximum Correlation (Stress Test)

Priority: P0
Correlation Rule Tested: Multiple rules stacking - Rule #1, #2, #3, #4, #24

Input:
Instagram username: rohan_official_99, Phone in bio: +91 99887 76655, Profile Pic A
Twitter username: rohan_official_99, Phone in bio: 09988776655, Profile Pic A (cropped)
Facebook username: rohan_official_99, Phone in bio: 9988776655, Profile Pic A
LinkedIn: name Rohan Mehta, employer matches FB, Profile Pic A
Telegram username: rohan_official_99, Phone in bio: 9988776655, Profile Pic A

Expected Results:
Rule #1 (Username, +30) triggers across IG/TW/FB/TG. Rule #2 (Phone, +30) triggers across IG/TW/FB/TG. Rule #4 (Profile Pic, +25) triggers across all 5. Rule #24 (LinkedIn Cross-Reference, +22) triggers. Aggregate score capped sensibly (system should NOT simply sum every rule infinitely - duplicate signal types across platform pairs should be deduplicated to avoid inflating beyond meaningful range). Final Tier: VERY HIGH (80+).

Pass Criteria: 5-platform identity cluster correctly resolves to VERY HIGH without runaway score inflation from duplicate-type signals.

----------------------------------------

TC-25: Database Lookup

Priority: P0
Feature Tested: Local sample database cross-reference

Input: Username from sample database

Expected Results:
Username matched against local sample DB. Returns: Phone number, Email, Address (if present in DB). No external API calls made for this lookup (local-only). Response time under 1 second (in-memory/indexed lookup).

Pass Criteria: Phone, email, and address correctly returned from local DB.

----------------------------------------

TC-26: Google Dorking

Priority: P1
Feature Tested: Search-engine dorking for cross-platform discovery

Input: Unique, low-collision username

Expected Results:
Dork queries constructed (e.g. site:*.com "username", intext:"username"). Returns profile URLs from platforms outside the standard catalog (Instagram/Twitter/Telegram/LinkedIn/GitHub/Reddit). Results deduplicated against already-known platforms. Each discovered URL tagged with source platform.

Pass Criteria: At least one profile found on an unexpected/uncatalogued platform.

----------------------------------------

TC-27: Multi-Platform - Instagram + Twitter + GitHub

Priority: P0
Correlation Rule Tested: Rule #1 (Exact Username Match) + Multi-Platform Aggregation

Input:
Instagram username: same_user_123
Twitter username: same_user_123
GitHub username: same_user_123

Expected Results:
Username found and confirmed on all 3 platforms. Each profile's data points independently extracted. Cross-Platform Correlation engine links all 3 as one identity cluster. Rule #1 triggered: Weight +30 (exact match across 3 platforms). Combined score reflects multi-platform confirmation. Tier: VERY HIGH (80+).

Pass Criteria: All 3 profiles found, correlated, and combined score reaches VERY HIGH tier.

----------------------------------------

TC-28: Adult Site Detection (Risk Flag)

Priority: P1
Feature Tested: Risk assessment flagging via Google dorking results

Input: Username found on an adult/NSFW platform via Google dorking (TC-26 output)

Expected Results:
Dorking result classified against an adult-platform domain list. Match triggers a "Risk Flag" on the subject's profile summary. Flag includes: source platform name, discovery method (dorking), and timestamp. Flagged result does NOT contribute to identity-correlation weight/score (kept separate from Cross-Platform Correlation engine). Sensitive-content handling: flagged URL stored but not auto-previewed/rendered.

Pass Criteria: Adult-platform match correctly flagged in risk assessment, excluded from correlation scoring.

----------------------------------------

Confidence Score Testing Matrix (Updated Weights)

Perfect Match: Username(30) + Phone(30) = 60 -> HIGH
Maximum Direct ID Match: Username(30) + Email(30) + Website(30) = 90 (capped/deduped) -> VERY HIGH
Strong Match: Username(30) + pHash(25) + Location(10) = 65 -> HIGH
LinkedIn-Anchored Match: LinkedIn Cross-Ref(22) + Username Pattern(20) = 42 -> MEDIUM
Developer-Platform Match: GitHub Email Cross-Ref(28) + GitHub Bio Links(26) = 54 -> MEDIUM (borderline HIGH)
Probable Match: Username Pattern(20) + Bio Text(15) + Timing(12) = 47 -> MEDIUM
Weak Match: Location(10) + Timing(12) = 22 -> LOW
Stylometric-Only (must stay LOW): Writing Style Match(12) only = 12 -> LOW
Different Person: Username Pattern(20) only, rest mismatch = 20 -> LOW

----------------------------------------

Sprint 1 Acceptance Criteria

MUST PASS (P0):
TC-01: 3-platform username match (VERY HIGH with corroboration)
TC-02: Phone match - Indian formats, weight 30
TC-03: Email match across platforms, weight 30
TC-04: Website/URL match, weight 30
TC-05: Profile picture pHash + face-embedding fallback
TC-06: Different person - LOW score (no false positive)
TC-07: Instagram business account contact info
TC-08: Twitter P0 points (11/13 min)
TC-09: Facebook work/education cross-ref
TC-10: LinkedIn P0 points (9/10 min)
TC-11: LinkedIn cross-reference with social platforms
TC-12: GitHub commit email cross-reference
TC-13: GitHub bio social links (native fields)
TC-14: Reddit social links in profile
TC-24: 5-platform stress test - no score inflation
TC-25: Database lookup returns phone, email, address
TC-27: Multi-platform (IG + Twitter + GitHub) correlation

SHOULD PASS (P1):
TC-15: Reddit self-disclosed info NLP extraction
TC-16: Telegram channel data
TC-17: Telegram phone sync (conditional)
TC-18: Private account handling
TC-19: Non-existent username error (all platforms)
TC-20: Bio link graph traversal
TC-26: Google dorking discovers uncatalogued platforms
TC-28: Adult site detection flagged in risk assessment

NICE TO PASS (P2):
TC-21: Cross-tagging detection
TC-22: Post timing correlation (Twitter and GitHub)
TC-23: Writing style stays capped at LOW alone

----------------------------------------

END OF DOCUMENT
