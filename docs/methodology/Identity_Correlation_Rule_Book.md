# AI-OSINT Identity Correlation Rule Book (v1.0)
### For Indian Law Enforcement Agencies - CONFIDENTIAL

**Core Principle:** This document defines the deterministic and heuristic rules the AI engine uses to calculate a confidence score, answering the question: "Are these two or more online identities the same real-world person?"

**Scoring Thresholds:**
- **≥ 90 points: MATCH CONFIRMED** (Definitely Same Person)
- **70 - 89 points: HIGH PROBABILITY** (Probably Same Person - Flag for Manual Verification)
- **50 - 69 points: POSSIBLE MATCH** (Might Be Same Person - Requires Corroborating Intel)
- **< 50 points: NO MATCH** (Insufficient Evidence - Probably Different Person)

**CRITICAL RULE:** The scoring is cumulative across all discovered platforms. A single **CONFIRMED** match immediately escalates the final verdict to `MATCH CONFIRMED`, regardless of the cumulative score.

---

### PART 1: UNIVERSAL HIGH-CONFIDENCE RULES (Platform Agnostic)
*These rules apply to any combination of platforms.*

#### 1.1 Unique Identifiers (Immediate CONFIRMED)
- **RULE 1.1.A: Exact Email Match**
    - **Condition:** Same email address found in Bio, About section, or any public profile field across two or more platforms.
    - **Score:** `CONFIRMED`
    - *Example: "lav.kumar@email.com" in Instagram bio and GitHub profile.*

- **RULE 1.1.B: Exact Phone Number Match**
    - **Condition:** Same Indian mobile number (+91 XXXXXXXXXX or 0XXXXXXXXXX format) found across platforms.
    - **Score:** `CONFIRMED`
    - *Example: "+91 98765 43210" in Telegram bio and Facebook About section.*

- **RULE 1.1.C: Government/Institutional ID Leak**
    - **Condition:** Same Aadhaar, PAN, Voter ID, Passport number, or Driving License number is detected in a post, bio, or document.
    - **Score:** `CONFIRMED` (and immediately flag the content for violation/review).

#### 1.2 Strong Biometric & Visual Links
- **RULE 1.2.A: Exact Profile Picture Match (Perceptual Hash)**
    - **Condition:** Identical image file (pHash match > 99.9%) used as profile picture on different platforms.
    - **Score:** `25` points per platform pair.
    - *Example: Same photo on Instagram and Twitter = 25 points.*

- **RULE 1.2.B: Profile Picture Face Match (Facial Recognition)**
    - **Condition:** Facial recognition vector match in profile pictures even if the images are different.
    - **Score:** `40` points per platform pair.
    - *Note: This is stronger than an exact image match as it indicates the same person in a different setting.*

- **RULE 1.2.C: Cross-Platform Media Face Cluster**
    - **Condition:** The same face repeatedly appears across posts, stories, or tagged photos on different platforms.
    - **Score:** `20` points per confirmed cross-platform cluster.

#### 1.3 Username Correlation
- **RULE 1.3.A: Exact Username Match**
    - **Condition:** Platform username string is identical.
    - **Score:** `30` points per platform pair.
    - *Example: "lavkumar" on Instagram AND "lavkumar" on Twitter = 30 points.*

- **RULE 1.3.B: Deterministic Username Pattern Variant**
    - **Condition:** Username follows a predictable, code-based pattern. The AI must extract a "base_username" and match it.
    - **Score:** `20` points per match.
    - **Patterns to code:**
        1.  **Numeric Suffix/Prefix:** `lavchaudharygc` -> `lavchaudharygc_1256854` | `lavchaudharygc123`
        2.  **Underscore/Hyphen/Dot Substitution:** `lav_chaudhary_gc` -> `lav.chaudhary.gc` -> `lav-chaudhary-gc` (Normalize by stripping these characters for comparison).
        3.  **Leet Speak:** `l4vch4udh4ry` -> `lavchaudhary`
        4.  **Common Indian Platform Prefix/Suffix:** `official_lav` -> `its_lav` -> `iamlav` -> `reallavkumar` -> `lavkumar_`

---

### PART 2: PLATFORM-SPECIFIC DEEP-DIVE RULES

#### 2.1 INSTAGRAM (`instagram.com`)
- **Data Points Scraped:** Profile Picture, Username, Full Name, Bio, #Posts, #Followers, #Following, External Link, Contact Info (Phone/Email), Business Category, Connected Accounts.
- **Content Scraped (Last 12 Posts):** Caption, Hashtags, Mentions, Collaborator Tags, Location Tags, Like Count, Comment Count, Media Type (image, video, carousel).

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **INSTA-BIO-01** | Cross-Platform Bio Keyword Match (Job/Role) | Same profession keyword detected in bio of another platform (e.g., "ethical hacker", "cyber crime investigator", "full stack dev"). | `+15` |
| **INSTA-BIO-02** | Cross-Platform Emoji Signature | Highly similar sequence of 3+ emojis in bios (e.g., 🕵️‍♂️💻🇮🇳). | `+10` |
| **INSTA-BIO-03** | Writing Style Vector Match | NLP-model similarity score of bio text > 85% compared to bio on another platform (same sentence structure, unique phrases). | `+20` |
| **INSTA-CONTACT-01** | Cross-Platform External Link Match | Same URL domain in profile link (e.g., `linktr.ee/lavkumar`). | `CONFIRMED` |
| **INSTA-POST-01** | Cross-Platform Hashtag Reuse | 5+ identical, non-generic hashtags used on posts across another platform (e.g., #lavkumarInvestigates). | `+15` |
| **INSTA-POST-02** | Cross-Platform Mention Correlation | An Instagram post mentions a Twitter handle (`@lavkumar`) that is under investigation. This strongly links the accounts. | `+25` |
| **INSTA-LOC-01** | Location Consistency | Geo-tagged post location is the same city as the location field on another profile (e.g., "Delhi, India"). | `+10` |

#### 2.2 TELEGRAM (`t.me` / Telegram App)
- **Data Points Scraped:** Profile Picture, Username, Display Name, Bio, Phone Number (if visible).
- **Activity Scraped (Public Channels/Groups):** Message text, forwarding patterns.

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **TG-USER-01** | Username-to-Phone Leak Link | Telegram username is found in a public database leak record that also contains a phone number matched to another platform. | `CONFIRMED` |
| **TG-BIO-01** | Bio-to-Bio Job/Role Match | Same specific job keyword as other platforms (Rule INSTA-BIO-01). | `+15` |
| **TG-BIO-02** | "Reserve" Username Link | Telegram bio states: "Reserve: @sameusername_as_other_platform". | `+40` |
| **TG-GROUP-01** | Common Group Membership | The subject is a member of the same niche, low-membership Telegram group as another known alias. | `+15` |

#### 2.3 FACEBOOK (`facebook.com`)
- **Data Points Scraped:** Profile Picture, Username/FB ID, Full Name, Intro/Bio, About (Work, Education, Location, Relationship, Family), Contact Info, External Links, #Followers.
- **Content Scraped (Public Posts):** Caption, Hashtags, Tagged People, Location, Like/Comment count.

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **FB-PROFILE-01** | Full Name-to-Username Correlation | Real name "Lav Chaudhary" on Facebook matches the name component of an email/username on another platform (`lav.chaudhary@email.com`). | `+20` |
| **FB-DETAILS-01** | Education/Workplace Match | "Studied at Delhi University" or "Works at XYZ Corp" on FB matches LinkedIn. | `+25` |
| **FB-DETAILS-02** | Family/Friends Graph Overlap | High degree of mutual friends or same family members tagged across two suspect profiles. | `+30` |
| **FB-BIO-01** | Status & Personal Details Match | Relationship status (e.g., "Married") and key personal details (e.g., "From Jaipur") are identical on another platform. | `+15` |
| **FB-EVENT-01** | Same Event Check-in | Both a suspect's profile and a witness's profile checked into the same event at the same time. | `+20` |

#### 2.4 WHATSAPP
- **Data Points Scraped (From Intel Dumps/Open Groups):** Display Name, About, Profile Picture. Phone number is the primary ID.

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **WA-ID-01** | Phone Number is King | A WhatsApp number is matched to any other platform's profile. | `CONFIRMED` |
| **WA-ABOUT-01** | About Text Match | The "About" text (e.g., "Life is a journey 🙏") is an exact match for an Instagram/Twitter bio snippet. | `+15` |
| **WA-NAME-01** | Display Name Pattern Match | Display name "Lav~GC" matches the pattern of a known username "lav_gc". | `+10` |

#### 2.5 LINKEDIN (`linkedin.com`)
- **Data Points Scraped:** Profile Picture, Name, Headline, About (Bio), Location, Education, Experience, Licenses, Featured Posts, #Followers, Contact Info.
- **Content Scraped (Activity/Posts):** Article text, Hashtags, tagged individuals.

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **LI-PRO-01** | Professional Timeline Match | A job change on LinkedIn perfectly matches a celebratory post and new bio on Twitter/Instagram. | `+25` |
| **LI-BIO-01** | "About" Section Copy-Paste | The full "About" section text on LinkedIn is a near-identical match to a GitHub README.md or a personal blog's "About Me" page. | `+30` |
| **LI-NET-01** | Cross-Platform Skill Endorsement | A skill endorsed on LinkedIn is a unique repo topic or Stack Overflow tag used by the subject. | `+10` |
| **LI-CONTACT-01** | LinkedIn Email to Other Platform | The contact email on a LinkedIn profile matches a WHOIS record, GitHub commit email, or other platform's signup leak. | `CONFIRMED` |

#### 2.6 GITHUB (`github.com`)
- **Data Points Scraped:** Profile Picture, Username, Full Name, Bio, Location, Email, Link/Blog URL, Organization, #Repos, Repository Names, Languages Used, Commit Patterns, README.md content.

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **GH-CODE-01** | Code-to-Identity Leak | A private key, API token, or configuration file in a public repo contains a username or email matched to another platform. | `CONFIRMED` |
| **GH-README-01** | README "Signature" Match | Writing style, emoji use, and personal branding in a README.md match an Instagram/LinkedIn bio style (Rule INSTA-BIO-03). | `+20` |
| **GH-EMAIL-01** | Commit-to-Profile Email Match | The email in a public `.patch` or commit log matches the email on a LinkedIn or Twitter account. | `CONFIRMED` |
| **GH-USER-01** | Username to NPM/PyPi/Docker Hub | GitHub username is identical to a handle on a related developer platform (e.g., `npmjs.com/~lavkumar`). | `+35` |

#### 2.7 YOUTUBE (`youtube.com`)
- **Data Points Scraped:** Channel Name, Handle, Profile Picture, Banner Image, About Section (Links, Email), #Subscribers, #Videos, Total Views.

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **YT-ABOUT-01** | Business Inquiry Email Link | The "For business inquiries" email on YouTube matches the public email on an Instagram or Twitter profile. | `CONFIRMED` |
| **YT-LINK-01** | Cross-Promotion Link Farm | The YouTube banner/About section links to the exact same Instagram, Twitter, and Telegram accounts as found on a personal blog. | `+30` |
| **YT-STYLE-01** | Comment-to-Bio Style Match | The writing style of the subject's comments on their own YouTube channel matches the bio style on another platform. | `+10` |

#### 2.8 REDDIT (`reddit.com`)
- **Data Points Scraped:** Username, Avatar, Banner, Bio/About, Active Subreddits, Post/Comment Content.

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **REDDIT-ID-01** | Direct Self-Dox Link | A Reddit post or comment explicitly states: "follow me on IG: @lavkumar". | `CONFIRMED` |
| **REDDIT-ACT-01** | Niche Community Overlap | The Reddit user frequents a city-specific subreddit (r/delhi) and a technical subreddit (r/hacking), matching the location and profession from LinkedIn. | `+15` |
| **REDDIT-ACT-02** | Unique Content Cross-Post | An image or text story posted to Reddit by u/lavkumar is watermarked with "@lavkumar" and later found on that Instagram account. | `CONFIRMED` |

#### 2.9 ADULT/NSFW & DELIVERY PLATFORMS
- **Data Points Scraped:** Username, Profile Bio, Listed Interests, Linked Accounts, Sex Toy Purchase Reviews (text, associated username), Profile Picture (face/body matching).

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **NSFW-ID-01** | Exact Username Link | A "clean" platform username (e.g., from LinkedIn) is used verbatim on a sex toy delivery site or adult content platform. | `CONFIRMED` |
| **NSFW-BIO-01** | Cross-Platform Kink/Interest Match | Specific interests listed in the NSFW bio (fetishes, roles) are matched using NLP to coded language in the subject's "clean" social media poetry, art, or alt accounts. | `+15` |
| **NSFW-PIC-01** | Partial Photo Correlation | A distinguishing, non-facial feature (tattoo, birthmark, watch, room background) in an NSFW profile picture matches a picture on Facebook or Instagram. | `+45` |
| **NSFW-PURCHASE-01** | Purchase Review Doxing | A product review on a sex toy site includes an image showing a reflection in the toy with the subject's face, or the review username is the same as their e-commerce account name. | `CONFIRMED` |

#### 2.10 INDIAN SHORT-VIDEO PLATFORMS (ShareChat, Moj, etc.)
- **Data Points Scraped:** Username, Display Name, Profile Picture, Bio, Content (video watermark/repost detection).

| Rule ID | Rule Description | Condition | Score |
| :--- | :--- | :--- | :--- |
| **DESI-SHORT-01** | TikTok Exile Match | Exact same username and profile picture migrated from a known, banned TikTok account to a Moj/ShareChat account. | `CONFIRMED` |
| **DESI-SHORT-02** | Cross-Platform Watermark | A video on Moj has an Instagram/YouTube watermark that matches the subject's known handle. | `CONFIRMED` |
| **DESI-BIO-01** | Vernacular Style Match | The use of specific Hindi/Hinglish dialect phrases and emojis in the bio matches the style on WhatsApp/Facebook posts. | `+20` |