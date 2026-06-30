# OSINT Identity Correlation Rules v1.0
## AI-Assisted OSINT Platform for Indian LEAs

---

## RULE CATEGORIES AND WEIGHTS

### CATEGORY 1: DIRECT IDENTIFIERS (Weight: 35%)

These are HARD PROOF. If these match, confidence is very high.

#### Rule 1.1: Exact Email Match
- **Condition:** Same email found in both profiles
- **Score:** +35 points (IMMEDIATE HIGH CONFIDENCE)
- **Confidence Impact:** CONFIRMED (>95%)
- **Example:** 
  - Instagram bio: "Contact: rahul@email.com"
  - Twitter bio: "Email: rahul@email.com"
- **Action:** Mark as CONFIRMED same person
- **Why:** Email is unique identifier, cannot be shared accidentally

#### Rule 1.2: Exact Phone Number Match
- **Condition:** Same phone number found in both profiles
- **Score:** +35 points (IMMEDIATE HIGH CONFIDENCE)
- **Confidence Impact:** CONFIRMED (>95%)
- **Example:**
  - Instagram bio: "+91 9876543210"
  - Telegram profile: "+91 9876543210"
- **Action:** Mark as CONFIRMED same person
- **Why:** Phone numbers are unique (especially with +91 India code)

#### Rule 1.3: Aadhaar/PAN/Document Number Match
- **Condition:** Same government ID referenced
- **Score:** +35 points
- **Confidence Impact:** CONFIRMED (>99%)
- **Note:** Rare in social media, but if found = definitive
- **Legal:** Handle with extreme caution per Indian data protection laws

---

### CATEGORY 2: STRONG USERNAME CORRELATION (Weight: 30%)

Username patterns strongly suggest same person.

#### Rule 2.1: Exact Username Match
- **Condition:** Same username string on both platforms
- **Score:** +30 points
- **Confidence Impact:** VERY HIGH (85-95%)
- **Example:**
  - Instagram: @rahul_sharma
  - Twitter: @rahul_sharma
- **Why:** Most people reuse exact username across platforms

#### Rule 2.2: Case Variation Match
- **Condition:** Same username but different capitalization
- **Score:** +28 points
- **Example:**
  - Instagram: @RahulSharma
  - Twitter: @rahulsharma
- **Why:** Case difference is cosmetic, same person

#### Rule 2.3: Leetspeak Normalization Match
- **Condition:** Username matches after number/symbol substitution
- **Score:** +20 points
- **Substitution Table:**
  - 4 = a, 3 = e, 1 = i/l, 0 = o, 5 = s, 7 = t, @ = a, $ = s
- **Example:**
  - Instagram: @r4hul_sh4rm4
  - Normalized: rahul_sharma
  - Twitter: @rahul_sharma
- **Why:** Leetspeak is conscious choice, same person pattern

#### Rule 2.4: Common Prefix/Suffix Pattern
- **Condition:** Base username same, only prefix/suffix differs
- **Score:** +18 points
- **Common Suffixes:** 
  - _official, _real, _insta, _yt, _fb, _twt, _x
  - _01, _123, _1 (number suffixes)
  - .official, .real
- **Common Prefixes:**
  - official_, real_, its_, the_, im_
- **Example:**
  - Instagram: @rahul_sharma
  - Twitter: @rahul_sharma_official
- **Why:** Platform-specific variations suggest same person managing accounts

#### Rule 2.5: Name Reversal or Rearrangement
- **Condition:** Username parts rearranged
- **Score:** +12 points
- **Example:**
  - Instagram: @sharma_rahul
  - Twitter: @rahul_sharma
- **Why:** Common in Indian naming (surname_firstname vs firstname_surname)

#### Rule 2.6: Platform-Specific Username Rules
- **Condition:** Username adapted to platform limitations
- **Score:** +15 points
- **Example:**
  - Instagram: @rahul.sharma (allows dots)
  - Twitter: @rahulsharma (no dots allowed)
- **Why:** Platform constraints force variations

---

### CATEGORY 3: IDENTITY ATTRIBUTES (Weight: 25%)

These are strong indicators but not unique.

#### Rule 3.1: Exact Full Name Match
- **Condition:** Complete name identical (first + last)
- **Score:** +25 points
- **Confidence Impact:** HIGH (80-90% if combined with other factors)
- **Example:**
  - Both profiles show "Rahul Sharma"
- **Important:** Common Indian names (Kumar, Singh, Sharma) have lower weight
  - Common name penalty: -5 points for very common surnames
- **Common Indian Surnames (reduce weight):**
  - Kumar, Singh, Sharma, Patel, Verma, Gupta, Yadav, Rajput

#### Rule 3.2: Partial Name Match
- **Condition:** First name matches, last name different or missing
- **Score:** +15 points
- **Example:**
  - Instagram: "Rahul Sharma"
  - Twitter: "Rahul S"
- **Why:** Common abbreviation pattern

#### Rule 3.3: First Name Only Match (Common Name)
- **Condition:** Only first name matches, common Indian name
- **Score:** +5 points
- **Common Indian First Names (low weight):**
  - Male: Rahul, Amit, Vikas, Sunil, Raj, Deepak, Manish, Ankit
  - Female: Priya, Neha, Pooja, Anjali, Shweta, Ritu, Kavita
- **Why:** Too many people share these names

#### Rule 3.4: First Name Only Match (Unique Name)
- **Condition:** Only first name matches, unique/uncommon name
- **Score:** +12 points
- **Unique Name Indicators:**
  - Less common in India
  - Combined names (e.g., Krishnakumar, Ramprasad)
  - Regional specific names
  - Modern/unique spellings
- **Why:** Unique names are stronger indicators

#### Rule 3.5: Display Name Variations (Indian Context)
- **Condition:** Name variations common in Indian context
- **Score:** +18 points
- **Acceptable Variations:**
  - With/without middle name: "Rahul K. Sharma" vs "Rahul Sharma"
  - Initials: "R.K. Sharma" vs "Rahul Sharma"
  - Title additions: "Dr. Rahul Sharma" vs "Rahul Sharma"
  - Caste/Community suffix: "Rahul Sharma (Brahmin)" vs "Rahul Sharma"
  - Professional prefix: "Adv. Rahul Sharma" vs "Rahul Sharma"
  - Regional variations: "Rahul" vs "Rahool" (same pronunciation)

---

### CATEGORY 4: PROFILE PICTURE CORRELATION (Weight: 20%)

Visual identity is very strong evidence.

#### Rule 4.1: Exact Image Match (Same File)
- **Condition:** Same image file (identical hash)
- **Score:** +20 points
- **Method:** MD5 or SHA256 hash comparison
- **Why:** Same exact file = very likely same person

#### Rule 4.2: Perceptual Hash Match (Similar Image)
- **Condition:** Images look the same (different sizes/crops)
- **Score:** +18 points
- **Method:** pHash distance < 5
- **Why:** Same photo used across platforms

#### Rule 4.3: Same Person, Different Photo
- **Condition:** Different photos but same individual
- **Score:** +15 points
- **Method:** Face recognition (if implemented)
- **Note:** Requires face recognition library
- **Why:** Strong evidence of same person

#### Rule 4.4: Similar Style/Theme
- **Condition:** Not same photo, not verified same person, but similar style
- **Score:** +5 points
- **Example:** Both use cartoon avatars, both use nature photos
- **Why:** Weak indicator but adds to cumulative score

#### Rule 4.5: Default/Absent Profile Picture
- **Condition:** One or both use default/no profile picture
- **Score:** +0 points (neutral)
- **Why:** Cannot correlate

---

### CATEGORY 5: BIOGRAPHICAL MATCHING (Weight: 15%)

Content analysis for identity correlation.

#### Rule 5.1: Bio Text High Similarity (>80%)
- **Condition:** Bio texts are very similar
- **Score:** +15 points
- **Method:** Cosine similarity of TF-IDF vectors
- **Example:**
  - Instagram: "Software developer | IIT Delhi | Open source lover"
  - Twitter: "Software engineer | IIT Delhi graduate | Open source contributor"
- **Why:** People describe themselves consistently

#### Rule 5.2: Bio Text Moderate Similarity (50-80%)
- **Condition:** Bios share keywords but different structure
- **Score:** +10 points
- **Why:** Same person may write differently for different platforms

#### Rule 5.3: Same Profession/Industry Mentioned
- **Condition:** Same job/industry stated
- **Score:** +8 points
- **Example:**
  - Both mention "Software Engineer"
  - Both mention "Doctor"
  - Both mention "Student"
- **Why:** Career is identifying but not unique

#### Rule 5.4: Same Educational Institution
- **Condition:** Same college/university mentioned
- **Score:** +8 points
- **Example:**
  - Both mention "IIT Delhi"
  - Both mention "Delhi University"
- **Why:** Education is strong correlator in Indian context

#### Rule 5.5: Same Organization/Company
- **Condition:** Same employer mentioned
- **Score:** +10 points
- **Example:**
  - Both mention "TCS"
  - Both mention "Infosys"
- **Why:** Employment is identifying

#### Rule 5.6: External Link Match
- **Condition:** Same website/linktree/portfolio linked
- **Score:** +15 points
- **Example:**
  - Both link to "rahulsharma.com"
  - Both link to same Linktree
- **Why:** Personal websites are unique

---

### CATEGORY 6: LOCATION MATCHING (Weight: 10%)

Geographic correlation.

#### Rule 6.1: Exact Location Match
- **Condition:** Same city/location mentioned
- **Score:** +10 points
- **Example:**
  - Both say "Mumbai"
  - Both say "Delhi NCR"
- **Why:** Location is identifying but many people share same city

#### Rule 6.2: Regional Match (Same State)
- **Condition:** Different cities but same state
- **Score:** +7 points
- **Example:**
  - Instagram: "Mumbai" (Maharashtra)
  - Twitter: "Pune" (Maharashtra)
- **Why:** Same state suggests same person

#### Rule 6.3: Location Contradiction
- **Condition:** Different locations that are far apart
- **Score:** -10 points (NEGATIVE - reduces confidence)
- **Example:**
  - Instagram: "Mumbai"
  - Twitter: "Kolkata"
- **Why:** Person likely lives in one place, not two distant cities
- **Exception:** If bio says "Originally from X, living in Y"

#### Rule 6.4: Multiple Locations (Work + Home)
- **Condition:** One profile shows work city, other shows home city
- **Score:** +8 points
- **Example:**
  - Instagram: "Working in Bangalore"
  - LinkedIn: "Native of Mysore, working in Bangalore"
- **Why:** Different cities can be work/home split

#### Rule 6.5: Vague Location Match
- **Condition:** Both say "India" or no specific city
- **Score:** +2 points
- **Why:** Too broad to be meaningful

---

### CATEGORY 7: SOCIAL GRAPH CORRELATION (Weight: 10%)

Who they interact with.

#### Rule 7.1: Mutual Followers/Connections
- **Condition:** Same accounts follow both profiles
- **Score:** +5 points per mutual connection (max +15)
- **Why:** Same social circle suggests same person

#### Rule 7.2: Cross-Tagging Pattern
- **Condition:** Both profiles tagged by same accounts
- **Score:** +8 points
- **Why:** Being tagged by same people suggests same identity

#### Rule 7.3: Same Accounts Mentioned
- **Condition:** Both profiles mention/reference same third accounts
- **Score:** +6 points
- **Why:** Referencing same accounts suggests shared identity

---

### CATEGORY 8: BEHAVIORAL & TECHNICAL (Weight: 10%)

How they use the platform.

#### Rule 8.1: Posting Time Pattern
- **Condition:** Active during same hours
- **Score:** +5 points
- **Why:** Same person posts during same free time

#### Rule 8.2: Content Type Consistency
- **Condition:** Same type of content (photos, text, memes, professional)
- **Score:** +5 points
- **Why:** Content preference is personal

#### Rule 8.3: Language Pattern
- **Condition:** Same languages used (English + Hindi mix, etc.)
- **Score:** +8 points
- **Why:** Language choice is personal, especially regional languages
- **Indian Context:**
  - Hinglish (Hindi + English mix): Common among North Indians
  - Tanglish (Tamil + English): Common in Tamil Nadu
  - Pure Hindi: More formal or rural
  - Pure English: Urban professional

#### Rule 8.4: Writing Style Analysis
- **Condition:** Similar vocabulary, emoji usage, punctuation style
- **Score:** +4 points
- **Why:** Writing style is like fingerprint but harder to quantify

#### Rule 8.5: Account Age Correlation
- **Condition:** Both accounts created around same time period
- **Score:** +3 points
- **Why:** Weak indicator but supports correlation

---

### CATEGORY 9: PLATFORM-SPECIFIC (Weight: 5%)

Platform behavior provides context.

#### Rule 9.1: Cross-Platform Linking
- **Condition:** One profile links to the other platform
- **Score:** +25 points (STRONG)
- **Example:**
  - Instagram bio: "Follow me on Twitter @rahul_sharma"
  - Twitter account exists as @rahul_sharma
- **Why:** Self-admission of ownership

#### Rule 9.2: Platform Consistency
- **Condition:** Same type of account on both (personal, business, creator)
- **Score:** +4 points
- **Why:** Same account type suggests same user

#### Rule 9.3: Follower Count Ratio
- **Condition:** Follower counts proportional across platforms
- **Score:** +2 points
- **Why:** Weak indicator

---

### CATEGORY 10: RED FLAGS & CONTRADICTIONS (Negative Points)

These REDUCE confidence.

#### Rule 10.1: Conflicting Personal Information
- **Condition:** Contradictory information that cannot be reconciled
- **Score:** -20 points
- **Example:**
  - Instagram: "Age 22, Student"
  - Twitter: "Age 35, Senior Manager"
- **Why:** Cannot be same person if age/profession don't match

#### Rule 10.2: Different Gender Indication
- **Condition:** Gender-specific names or pronouns don't match
- **Score:** -25 points
- **Example:**
  - Instagram: "Rahul" (male) + male photos
  - Twitter: "Priya" (female) + female photos
- **Why:** Gender mismatch = different person (unless transgender context)

#### Rule 10.3: Impossible Location Split
- **Condition:** Active in two countries simultaneously
- **Score:** -15 points
- **Example:**
  - Instagram: Daily posts from India
  - Twitter: Daily posts from USA (same time period)
- **Why:** Cannot be in two countries at once

#### Rule 10.4: Completely Different Interest/Lifestyle
- **Condition:** No overlap in content, interests, or lifestyle
- **Score:** -10 points
- **Example:**
  - Instagram: Religious content, traditional
  - Twitter: Adult content, party lifestyle
- **Why:** Dramatic lifestyle difference suggests different people

#### Rule 10.5: Verified vs Unverified Contradiction
- **Condition:** One account verified (celebrity), other unverified with no following
- **Score:** -15 points
- **Why:** Likely impersonator account

---


## SCORING ALGORITHM

### How to Calculate:

STEP 1: Start with 0 points as your base score

STEP 2: Go through each rule category one by one:
   - Category 1: Direct Identifiers (Email, Phone, Documents)
   - Category 2: Username Correlation
   - Category 3: Identity Attributes (Name)
   - Category 4: Profile Picture
   - Category 5: Biographical Content
   - Category 6: Location
   - Category 7: Social Graph
   - Category 8: Behavioral & Technical
   - Category 9: Platform-Specific
   - Category 10: Red Flags & Contradictions

STEP 3: Add points for every rule that matches positively
   Example: Email matches → Add +35 points
   Example: Username matches → Add +30 points
   Example: Same location → Add +10 points

STEP 4: Subtract points for contradictions and red flags
   Example: Different locations far apart → Subtract -10 points
   Example: Different gender indication → Subtract -25 points
   Example: Impossible age difference → Subtract -20 points

STEP 5: Calculate the total score by adding all positive points and subtracting all negative points
   Formula: TOTAL SCORE = (Sum of all positive matches) - (Sum of all negative contradictions)

STEP 6: Apply Indian Context Adjustments if needed:
   - If name is very common (Kumar, Singh, Sharma): Reduce name match points by 5
   - If regional language matches: Add +5 bonus
   - If locations are different spellings of same place: No penalty (e.g., Bangalore = Bengaluru)

STEP 7: Convert the final score to a confidence percentage using the table below

---

### Confidence Scale and Decision Matrix:

| Total Score Range | Confidence Percentage | Final Decision | Recommended Action |
|-------------------|----------------------|----------------|-------------------|
| 80 to 100+ points | 95% to 100% | DEFINITELY SAME PERSON | Proceed with investigation. High confidence. No additional verification needed for identity correlation. Use consolidated identity. |
| 60 to 79 points | 80% to 94% | VERY LIKELY SAME PERSON | Proceed with investigation. Note high confidence in report. Minor verification recommended but not critical. |
| 40 to 59 points | 60% to 79% | PROBABLY SAME PERSON | Proceed with caution. Flag for manual verification before taking major action. Look for additional data points to increase confidence. |
| 20 to 39 points | 40% to 59% | POSSIBLY SAME PERSON | Insufficient evidence. Need more data from additional platforms or sources. Do not make conclusions yet. Flag for further investigation. |
| 0 to 19 points | 10% to 39% | UNLIKELY SAME PERSON | These are probably different people. Investigate each profile separately. Only pursue if other intelligence strongly suggests connection. |
| Below 0 points (Negative) | Below 10% | DEFINITELY DIFFERENT PERSON | Stop correlation attempt. These are different individuals. Investigate as separate entities. Do not waste resources linking them. |

---

### Important Notes for Scoring:

NOTE 1: Some rules have MAXIMUM CAPS
   - Rule 7.1 (Mutual Followers): Maximum +15 points even if 10+ mutual connections found
   - This prevents any single category from dominating the score unfairly

NOTE 2: CONFIRMED rules override the scoring system
   - Email match (Rule 1.1): If found, automatically set confidence to 95%+ regardless of other scores
   - Phone match (Rule 1.2): If found, automatically set confidence to 95%+ regardless of other scores
   - Government ID match (Rule 1.3): If found, automatically set confidence to 99%+
   - These are HARD PROOFS that don't need other evidence

NOTE 3: Contradictions can cancel matches
   - If you have +35 for email match but -25 for gender mismatch → INVESTIGATE MANUALLY
   - Something is wrong — possibly a shared/compromised account or data error
   - Flag for human review immediately

NOTE 4: Minimum data requirement
   - If less than 3 data points available for comparison → Score is automatically "INSUFFICIENT DATA"
   - Do not force correlation with too little information
   - Return "Need more data" instead of guessing

NOTE 5: AI vs Rule-Based Scoring
   - Rules provide the mathematical score
   - AI provides the natural language explanation
   - If AI disagrees with the score → Flag for human review
   - Example: Score says 85% but AI says "MAYBE" → Human investigator must review