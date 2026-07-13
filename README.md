# 🔍 AI-OSINT Investigation Engine

> **AI-powered Open Source Intelligence platform for cross-platform identity correlation, social media profiling, and digital footprint analysis.**
> Built for authorized Law Enforcement and Cybersecurity investigations.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![OSINT](https://img.shields.io/badge/Category-OSINT-red.svg)](https://en.wikipedia.org/wiki/Open-source_intelligence)
[![Status](https://img.shields.io/badge/Status-Active%20Development-orange.svg)]()

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Data Extraction Specification](#data-extraction-specification)
- [AI Training Datasets](#ai-training-datasets)
- [Installation](#installation)
- [Usage](#usage)
- [API Integration](#api-integration)
- [UI Enhancement Ideas](#ui-enhancement-ideas)
- [Safety & Legal Guidelines](#safety--legal-guidelines)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

The **AI-OSINT Investigation Engine** is a comprehensive platform designed to:

- **Scrape and analyze** public Instagram profiles for investigative intelligence
- **Correlate identities** across multiple social platforms using AI-powered matching
- **Detect impersonators** and fake celebrity accounts
- **Extract enriched data** including bios, posts, hashtags, contacts, and cross-platform links
- **Generate official investigation reports** with confidence scoring

### Key Capabilities

| Capability | Description |
|-----------|-------------|
| 🔍 **Profile Scraping** | Extract 38+ data points from Instagram profiles |
| 🤖 **AI Identity Matching** | Cross-platform correlation with confidence scoring |
| 🏷️ **Hashtag Analysis** | Link accounts via distinctive personal-brand hashtags |
| 🎭 **Impersonator Detection** | Identify fake accounts using structural red flags |
| 📊 **Threat Scoring** | Generate risk scores and investigation reports |
| 📱 **Contact Enrichment** | Discover phone numbers via LinkedIn + SignalHire integration |

---

## ✨ Features

### 1. Instagram Data Extraction (38+ Fields)

Extracts comprehensive profile intelligence including:

- **Basic Identity**: Username, Full Name, Bio, Profile Picture, Verified Status
- **Engagement Metrics**: Followers, Following, Post Count, Account Type
- **Contact Info**: Email, Phone, Address (Business accounts), External URLs
- **Content Analysis**: Last 12 posts, captions, hashtags, timestamps, location tags
- **Network Mapping**: Tagged users, mentioned users, comments, collab posts
- **Account History**: Creation date, former usernames, active ads, country/region
- **Cross-Platform Links**: Linked Facebook, YouTube, GitHub, LinkedIn references

> 📄 **Full specification**: See [`Instagram_OSINT_DataSpec_v2.xlsx`](docs/Instagram_OSINT_DataSpec_v2.xlsx)

### 2. AI-Powered Identity Correlation

Trained on **36+ real-world examples** across 6 confidence tiers:

| Confidence Tier | Range | Example Cases |
|------------------|-------|---------------|
| 🔴 **VERY HIGH** | 90-100% | Same username + cross-linked bios + matching content |
| 🟠 **HIGH** | 75-90% | Similar username + brand anchor + bidirectional bio refs |
| 🟡 **MEDIUM-HIGH** | 70-85% | Distinctive hashtag patterns + follower count corroboration |
| 🟢 **MEDIUM** | 50-65% | Founder/company relationship detection |
| 🔵 **LOW-MEDIUM** | 30-50% | Similar usernames but different demographics |
| ⚪ **LOW** | 0-20% | No relation — coincidental name/brand overlap |

#### Correlation Categories:

- ✅ **Same Username → Same Person** (e.g., `arkagrawall` across IG/Twitter/GitHub/LinkedIn)
- ⚠️ **Similar Username → Same Person** (e.g., `jatinjangir` vs `jatinjangir_`)
- 🚫 **Similar Username → Different Person** (e.g., two different `Sumit Shah`s)
- 🎭 **Different Username → Same Person** (e.g., `bhuvan.bam22` → `BBKiVines`)
- 🏢 **Company vs Personal Account** (e.g., `tacsecurity` vs `trishneetarora`)
- 👻 **Impersonator Detection** (fake `carryminati` accounts)
- 🏷️ **Hashtag-Based Linking** (e.g., `#dutchosintguy` personal brand)

> 📄 **Training Data**: See [`Sprint_1_OSINT_AI_Training.json`](data/training/Sprint_1_OSINT_AI_Training.json) and [`Sprint_2_OSINT_Hashtags.json`](data/training/Sprint_2_OSINT_Hashtags.json)

### 3. Contact Enrichment via SignalHire

**Idea**: When a LinkedIn profile is discovered during investigation, use **SignalHire** browser extension/API to extract:

- 📞 **Phone numbers** associated with the profile
- 📧 **Personal/Work email addresses**
- 💼 **Employment history** and contact details

**Integration Flow:**
```
Instagram Profile → Cross-Platform Discovery → LinkedIn Found 
    → SignalHire API Call → Enriched Contact Data → Investigation Report
```

> 🔑 **API Key**: Store securely in environment variables (see `.env.example`)

### 4. Subject Identity Card (UI Enhancement)

Proposed **Subject Identity Panel** displaying:

```
┌─────────────────────────────────────────┐
│  [PROFILE PIC]  sumit_._shah_           │
│               ─────────────────         │
│  Name:        Sumit Shah                │
│  Location:    Mumbai                    │
│  Bio:         S/W Dev | Tech Enthusiast │
│  Followers:   12.5k                     │
│  Following:   870                       │
│  Verified:    False                     │
│  Status:      ACTIVE                    │
│  Scraped At:  2026-06-30 05:29:29       │
│  Case ID:     UPP-CASE-2026-088110      │
└─────────────────────────────────────────┘
```

> 🖼️ **UI Mockup**: See [`ui_mockup_subject_identity_card.jpeg`](docs/ui_mockup_subject_identity_card.jpeg)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI-OSINT ENGINE                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Instagram  │  │   Apify     │  │   SignalHire API    │ │
│  │  Scraper    │  │   Actors    │  │   (Contact Enrich)  │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │            │
│         └────────────────┼─────────────────────┘            │
│                          ▼                                  │
│              ┌─────────────────────┐                        │
│              │  Data Normalization │                        │
│              │  & Feature Extraction│                       │
│              └──────────┬──────────┘                       │
│                         ▼                                   │
│              ┌─────────────────────┐                        │
│              │  AI Correlation     │                        │
│              │  Engine (DeepSeek)  │                        │
│              │  Confidence Scoring │                        │
│              └──────────┬──────────┘                       │
│                         ▼                                   │
│              ┌─────────────────────┐                        │
│              │  Subject Identity   │                        │
│              │  Card + Report Gen  │                        │
│              └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 Data Extraction Specification

### Extractable Data Points (Public Accounts)

| # | Field | Source | Investigation Value |
|---|-------|--------|---------------------|
| 1 | Username | Profile page | Primary cross-platform identifier |
| 2 | Full Name | Below profile pic | Real identity clue |
| 3 | Bio Text | Below full name | Emails, phones, links, locations |
| 4 | Profile Picture | Left side | Reverse image search, face match |
| 5-7 | Followers/Following/Posts | Stats row | Bot detection, influence gauging |
| 8 | External URL | Bio section | Cross-platform link discovery |
| 9 | Verified Status | Blue tick badge | Identity confirmation |
| 10 | Business Category | Business accounts | Profession/industry reveal |
| 11-12 | Account Creation Date | "About This Account" | Account age = credibility signal |
| 13-14 | Former Usernames | "About This Account" | Identity change tracking |
| 15-18 | Last 12 Posts | Profile grid | Behavior patterns, interests, associates |
| 19-22 | Hashtags, Timestamps, Locations, Tags | Post metadata | Activity mapping, network analysis |
| 23-26 | Contact Info (Email/Phone/Address) | Business accounts | Direct tracing via Truecaller/police |
| 27-38 | Pinned Posts, Collabs, Story Highlights, etc. | Various | Priority content, close associates |

### Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Public — freely extractable via Instaloader or public HTTP |
| ⚠️ | Partial — depends on privacy settings, login, or API limits |
| ❌ | Private — requires court order or Meta cooperation |

> 📄 **Full 38-point spec with extraction methods**: [`Instagram_OSINT_DataSpec_v2.xlsx`](docs/Instagram_OSINT_DataSpec_v2.xlsx)

---

## 🤖 AI Training Datasets

### Sprint 1: Cross-Platform Identity Correlation
**File**: [`Sprint_1_OSINT_AI_Training.json`](data/training/Sprint_1_OSINT_AI_Training.json)

- **15 real-world examples** (IDs 6-20)
- Covers: Same username, similar username, different username patterns
- Includes: Instagram → Twitter/X, LinkedIn, GitHub, YouTube, personal websites
- **Key lesson**: Common names (e.g., "Sumit Shah") create false positives — demographics and content context are primary identifiers

### Sprint 2: Hashtag-Based Identity Linking
**File**: [`Sprint_2_OSINT_Hashtags.json`](data/training/Sprint_2_OSINT_Hashtags.json)

- **21 real-world examples** (IDs 21-36)
- Covers: Personal-brand hashtags, generic hashtag traps, impersonator detection
- Includes: Celebrity cases (Bhuvan Bam, CarryMinati, Technical Guruji)
- **Key lessons**:
  - Distinctive personal-brand hashtags (`#dutchosintguy`) > generic tags (`#osint`)
  - Bidirectional bio tagging is gold-standard for identity linking
  - Founder/company relationships must be modeled separately from personal aliases
  - Verified badge + follower count disparity = reliable impersonator detection

### Training Data Structure

```json
{
  "example_id": 21,
  "category": "DIFFERENT_USERNAME_SAME_PERSON",
  "confidence_tier": "HIGH (90-100%)",
  "input": {
    "primary_profile": { /* Instagram profile data */ },
    "discovered_profiles": [ /* Cross-platform matches */ ]
  },
  "expected_output": {
    "platform_matches": [ /* Confidence scores & reasons */ ],
    "consolidated_identity": { /* Unified profile */ }
  }
}
```

---

## 🚀 Installation

### Prerequisites

```bash
# Python 3.10+
python --version

# Install dependencies
pip install -r requirements.txt
```

### Core Dependencies

```txt
fastapi>=0.111
pydantic-settings>=2.2
httpx>=0.27
instaloader>=4.13
telethon>=1.44,<2
```

### Environment Setup

```bash
cp .env.example .env

# Edit .env with your credentials:
# APIFY_API_TOKEN=your_apify_token_here
# SIGNALHIRE_API_KEY=your_signalhire_key_here
# RAPIDAPI_KEY=your_rapidapi_key_here
```

---

## 💻 Usage

### Basic Profile Scan

```python
from osint_engine import InstagramScanner, IdentityCorrelator

# Initialize scanner
scanner = InstagramScanner(
    apify_token="your_token",
    rate_limit_delay=3  # seconds between requests
)

# Scan target profile
profile = scanner.scan_profile("target_username")

# Correlate across platforms
correlator = IdentityCorrelator(training_data="data/training/")
results = correlator.correlate(profile)

# Generate report
report = correlator.generate_report(results)
report.export_pdf("investigation_report.pdf")
```

### One-click cross-platform investigation

One normal username request starts the complete collection workflow. The selected
`platform` remains the primary profile used for normalization and correlation,
but it does not limit collection to that platform.

```bash
curl -X POST http://127.0.0.1:8010/api/v1/investigation/username \
  -H "Content-Type: application/json" \
  -d '{"username":"target_user","platform":"instagram","case_id":"CASE-001","correlation_depth":2}'
```

For a normal username, the backend launches these nine Apify Actor runs
concurrently: Instagram profile, Instagram posts, Twitter profile and replies,
Twitter search, Reddit, LinkedIn profile/company, LinkedIn posts, Facebook Pages,
and Facebook posts. The safe Telegram public/authorized lookup also starts in
the same workflow. Results are returned under `apify_social_results`. Its
`actors` object contains nine stable per-Actor entries, `summary` counts their
outcomes, `telegram` contains the separate Telegram result, and `mode` is
`automatic_all_actors` for normal usernames. Actor entries include available
run/dataset provenance. One Actor failure is reported as a partial failure and
does not discard successful results from the other collectors.

Each Actor can create a separate Apify charge or require a paid Actor
subscription, and the combined request can take multiple minutes. Apify-backed
Google dorking uses additional capacity beyond these nine social Actor runs. A matching
username on another platform is only an identity candidate; corroborate it with
bios, links, content, location, and other evidence before treating it as the
same person.

Telegram invite links are the exception. They use `mode: "privacy_guard"`, are
handled as isolated, read-only previews, and are never sent to Apify,
cross-platform search, dorking, AI, databases, or reporting providers.

### Using an explicit Apify Actor endpoint

The explicit Actor endpoints remain available when only one targeted collector
is needed. Calling one of these routes is separate from the one-click workflow
and can incur an additional Actor run.

```bash
curl -X POST http://127.0.0.1:8010/api/v1/apify/twitter/profile \
  -H "Content-Type: application/json" \
  -d '{"username":"target_user","max_items":50,"get_replies":true}'
```

### Rate Limiting

> ⚠️ **Max ~200 requests/hour** on Instagram. Add random delays of 2-5 seconds between requests to avoid blocks.

---

## 🔌 API Integration

### Supported APIs & Tools

| Service | Purpose | Documentation |
|---------|---------|---------------|
| **Apify** | Instagram, Twitter, Reddit, LinkedIn, and Facebook public-data actors | [apify.com](https://apify.com) |
| **SignalHire** | Contact enrichment (phone/email from LinkedIn) | [signalhire.com](https://signalhire.com) |
| **RapidAPI** | Fallback Instagram scraper | [rapidapi.com](https://rapidapi.com) |
| **Instaloader** | Primary Python library for IG extraction | [instaloader.github.io](https://instaloader.github.io) |

### Apify Actor Recommendations

| Actor | Use Case |
|-------|----------|
| `apify/instagram-profile-scraper` | Instagram profile metadata extraction |
| `apify/instagram-scraper` | Instagram post and reel collection |
| `apify/instagram-hashtag-scraper` | Hashtag-based post discovery |
| `apidojo/twitter-profile-scraper` | Twitter profile tweets and their replies |
| `apidojo/tweet-scraper` | Twitter/X post and advanced-query search |
| `automation-lab/reddit-scraper` | Reddit posts, comments, user history, and search |
| `bebity/linkedin-premium-actor` | LinkedIn profiles and companies in bulk |
| `apimaestro/linkedin-posts-search-scraper-no-cookies` | LinkedIn public post search |
| `apify/facebook-pages-scraper` | Facebook public Page metadata |
| `apify/facebook-posts-scraper` | Facebook public Page posts |
| `coderx/instagram-profile-scraper-bio-posts` | Bio + posts combined scrape |

---

## 🎨 UI Enhancement Ideas

### Subject Identity Card Panel

Proposed dashboard component showing consolidated subject intelligence:

```
┌────────────────────────────────────────────────────┐
│ CASE: UPP-CASE-2026-088110    [Export PDF] [🟢]  │
├────────────────────────────────────────────────────┤
│  [📷]  @sumit_._shah_              Score: 65%    │
│  ───────────────────────────────────────────────   │
│  📛 Name:        Sumit Shah                        │
│  📍 Location:    Mumbai                            │
│  💼 Bio:         S/W Dev | Tech Enthusiast         │
│  👥 Followers:   12.5k    Following: 870           │
│  ✅ Verified:    False                             │
│  🟢 Status:      ACTIVE                            │
│  🕐 Scraped:     2026-06-30 05:29:29               │
│  ───────────────────────────────────────────────   │
│  CROSS-PLATFORM PRESENCE:                          │
│  [Instagram 🟢] [Twitter 🔴] [LinkedIn 🟡]        │
│  [Telegram 🟢]  [GitHub 🔴]   [Reddit 🔴]          │
└────────────────────────────────────────────────────┘
```

### Features to Implement

- [ ] **Real-time correlation score** with animated gauge
- [ ] **Platform presence matrix** with HTTP status indicators
- [ ] **One-click PDF export** for official investigation reports
- [ ] **Timeline view** of account activity and post history
- [ ] **Network graph** of tagged/mentioned user relationships
- [ ] **Dark mode** optimized for extended investigation sessions

> 🖼️ **Mockup Reference**: [`WhatsApp_Image_2026-06-30_UI_Mockup.jpeg`](docs/ui_mockup.jpeg)

---

## ⚖️ Safety & Legal Guidelines

### ⚠️ CRITICAL RULES

1. **Authorized Use Only** — This tool is for authorized Law Enforcement and licensed investigators
2. **Case ID Logging** — Every extraction must be logged with a unique case ID
3. **Rate Limiting** — Never exceed 200 requests/hour. Use random delays (2-5s)
4. **Private Accounts** — Most data returns empty/blocked. Respect privacy settings
5. **No Illegal Access** — Do NOT attempt to access DMs, IPs, or backend Meta data
6. **Court Orders** — For private data (DMs, device info), proper legal process is required

### Legal Notice

> This tool is for **authorized Law Enforcement use only**. All extractions must be logged with case ID. Unauthorized use may violate platform Terms of Service and applicable privacy laws.

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Contribution Areas

- 🌍 Additional platform scrapers (TikTok, Telegram, Discord)
- 🤖 More AI training examples for edge cases
- 🎨 UI/UX improvements and dashboard components
- 📚 Documentation and use-case guides
- 🔒 Security enhancements and anonymization features

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

> **Disclaimer**: This tool is intended for legal, authorized investigations only. Users are responsible for complying with all applicable laws and platform terms of service.

---

## 📎 External Documentation

Additional project documentation and research files:

- 📄 [Google Doc 1 — Project Research & Notes](https://drive.google.com/file/d/1maRJUrxyB2W7unQ0_zSlSy-h17-QZ6mR/view?usp=drive_link)
- 📄 [Google Doc 2 — Additional Specifications](https://drive.google.com/file/d/1A5RJ_E7vyhq2eB8yfTU3CHlWQkrFVTWt/view?usp=drive_link)

## 🙏 Acknowledgments

- **Apify** for reliable social media scraping infrastructure
- **SignalHire** for contact enrichment capabilities
- **Instaloader** community for Instagram extraction tools
- All contributors to the OSINT and cybersecurity community

---

## 📬 Contact

For questions, suggestions, or collaboration:

- 📧 Email: [sumitshahpvt@gmail.com](mailto:sumitshahpvt@gmail.com)
- 📸 Instagram: [@sumit_._shah_](https://instagram.com/sumit_._shah_)
- 💼 LinkedIn: [Sumit Shah](https://www.linkedin.com/in/sumit-shah-934386392/)

---

<div align="center">

**⭐ Star this repo if you find it useful! ⭐**

*Built with ❤️ for the OSINT community*

</div>
