# RISK ASSESSMENT — Rules & Backend Specification
### AI-OSINT tool · Indian law-enforcement context
*Reference for the backend developer. Defines how the AI scores a profile for risk and what it must return.*

---

## 0. Read first — non-negotiable principles

1. **A risk score is an investigative lead, not a verdict.** No automated score may, on its own, arrest, charge, detain, publicly name, or take coercive action against a person. It routes accounts to human analysts.
2. **Human gate on the top tier.** Any "Escalate / Immediate Action" outcome must be reviewed and authorized by a human before anything happens in the real world.
3. **Lawful basis required.** Only assess data collected under a specific, authorized purpose. Route scope/retention/authorization to legal/compliance. Likely relevant: *DPDP Act 2023*, *IT Act 2000 & Rules*, *BNS 2023* offence definitions, and the *Puttaswamy (2017)* privacy standard. This document is not legal advice.
4. **Protected characteristics are never risk indicators** (Section 5). Religion, caste, region, language, gender, sexual orientation, political opinion, and lawful dissent must not raise a score. If the model's evidence for risk reduces to any of these, the correct output is **low risk**.
5. **Low data ≠ low risk. Low data = low confidence.** Report confidence separately; when data is thin, default to *Monitor / collect more*, not to a high score.
6. **Explain every point.** Each score ships with an itemized evidence list a human can audit and challenge.

---

## 1. How scoring works

- Each **risk category** (Section 3) produces its own **sub-score 0–100** from weighted indicators, capped at 100.
- Indicators inside a category are **additive up to the cap**; correlated indicators (two expressions of the same fact) count once.
- **Disconfirming / benign context subtracts** within the category.
- **Overall risk = the highest category sub-score**, plus a small **+10 multi-category boost** if two or more independent categories each score ≥ 50 (capped at 100). Rationale: an account that is clearly a sextortion vector is high-risk even if its "bot score" is low — max, not average, protects victims.
- **Confidence (0–100)** is computed separately from *data completeness* (how many expected fields were available). Low confidence caps the recommended action at *Investigate*, never *Immediate Action*.

---

## 2. Category weight priority

| Priority | Category | Why prioritized |
|---|---|---|
| Highest | Child safety (protective routing) | Imminent harm to a minor |
| Highest | Credible threat / incitement to violence | Imminent harm to a person |
| High | Sextortion & NCII | Active coercion, high victim self-harm risk |
| High | Harassment / stalking | Active victim, escalation risk |
| High | Scam / fraud (active victims) | Ongoing financial loss |
| Medium | Impersonation | Enabler for fraud & harassment |
| Medium | Illicit sale / trafficking / money-mule | Serious but usually non-imminent |
| Lower | Bot / fake / coordinated inauthenticity | Infrastructure signal, rarely urgent alone |

---

## 3. Risk categories, indicators, and weights

Weights are **starting values** — tune against labeled data. `(−)` marks disconfirming context that subtracts.

### 3.1 Scam / Fraud
| Indicator | Weight |
|---|---:|
| Financial solicitation / payment request to strangers (UPI ID, QR "scan to receive", account/wallet, gift cards) | +25 |
| Impersonation of a bank, govt body, courier, or known figure | +30 |
| Guaranteed/too-good returns, fixed-profit "investment/tip" language | +25 |
| Urgency + threat ("account blocked in 2 hrs", "warrant", "pay now") | +20 |
| Recently created account + high-volume outreach/DMs | +15 |
| Off-platform push to WhatsApp/Telegram + a phone number | +15 |
| Fake/SEO "customer care" number in bio/posts | +20 |
| Reused scam script / identical copy across many accounts | +20 |
| Links to newly-registered / look-alike domains | +15 |
| `(−)` Registered business, verified merchant, disclosed T&Cs, real refund policy | −25 |
| `(−)` Legitimate crowdfunding/fundraiser with named beneficiary & receipts | −20 |

*See Appendix A for the India scam-typology patterns the model should match against.*

### 3.2 Bot / Fake / Coordinated inauthenticity
| Indicator | Weight |
|---|---:|
| Follower/following ratio anomaly (extreme either direction) | +15 |
| Generic / stock / AI-generated profile photo (reverse-image or AI-detect) | +15 |
| Handle = name + random digit string | +10 |
| Automated cadence (fixed intervals, 24×7 posting) | +20 |
| No original content — only reshares/links | +15 |
| Identical comment/caption text posted across many accounts | +20 |
| Cluster of accounts created same day, similar bios | +20 |
| `(−)` Long history, personal photos, human-varied activity, real-world footprint | −25 |

### 3.3 Harassment / Stalking
| Indicator | Weight |
|---|---:|
| Multiple accounts targeting the same victim | +30 |
| Obsessive commenting/DMing (high frequency, one target) | +25 |
| Posting the victim's private data — address, phone, workplace (doxxing) | +30 |
| Location-tracking / surveillance language ("I saw you at…", "I know where you are") | +25 |
| Following the victim across platforms after being blocked | +20 |
| Threats of violence toward the victim | +30 |
| Coordinated pile-on / brigading against one target | +20 |
| `(−)` Public-interest criticism of a public figure/institution, no targeting of private data or person | −25 |

### 3.4 Sextortion & NCII (non-consensual intimate imagery)
| Indicator | Weight |
|---|---:|
| Threats to leak intimate images unless paid / complied with | +40 |
| Video-call-blackmail pattern (rapid trust-build → recorded call → demand) | +35 |
| Distributing or advertising a person's intimate images without consent | +40 |
| Coercive "send more or I post" language | +35 |
| Payment demand tied to the above | +20 |

> High victim self-harm risk. Any hit here → escalate to a human and route to the appropriate unit / victim-support pathway. Handle victim data with maximum minimization.

### 3.5 Impersonation
| Indicator | Weight |
|---|---:|
| Copied name + photo of a real person/brand/official on a separate account | +30 |
| Account used to solicit money/data while posing as that entity | +25 |
| Look-alike handle (added char, swapped letter) of a known account | +20 |
| `(−)` Clearly labelled parody/fan/commentary account | −30 |

### 3.6 Child safety — protective routing (do not detail offender tradecraft)
| Indicator (behavioral flags only) | Weight |
|---|---:|
| Adult account systematically initiating private contact with minors | +40 |
| Solicitation / distribution / advertising of child sexual abuse material | +100 → auto-max |
| Requests to move a minor to secret/encrypted channels or to hide contact from guardians | +35 |

> **Any hit → immediate escalation to the designated child-protection / specialized cyber unit.** This category does not attempt to "investigate" further inside the tool; it routes. Never generate, reconstruct, or store the illicit content itself; log the referral and evidence pointer only, per your CSAM-handling legal protocol.

### 3.7 Credible threat / incitement to violence (narrow)
| Indicator | Weight |
|---|---:|
| Specific, credible threat of violence against an identifiable person/place | +40 |
| Organizing/mobilizing for imminent violent action (time, place, means) | +35 |
| Direct incitement to attack a specific target | +30 |
| `(−)` Political/religious/social opinion, protest, dissent, or rhetoric **without** a specific credible call to imminent violence | **hard −, do not flag** |

> This category is walled: it fires on **specific credible incitement to imminent violence only**. Ideology, religion, caste, dissent, and offensive-but-lawful speech are **out of scope** and must not raise the score. When in doubt here, score low and let a human decide — the cost of over-flagging protected expression is high.

### 3.8 Illicit sale / trafficking / money-mule (medium)
| Indicator | Weight |
|---|---:|
| Coded product menus + price lists + "delivery to your area" for controlled goods | +25 |
| Advertising persons for exploitation / trafficking indicators | +35 |
| Recruiting for "receive & forward money" (mule) roles | +25 |
| Selling stolen data / OTPs / bank drops / fake documents | +30 |

---

## 4. Risk bands → recommended action

| Overall score | Band | Recommended action |
|---|---|---|
| 0–24 | **Minimal** | No action / passive monitor |
| 25–49 | **Low–Moderate** | Monitor, enrich data |
| 50–74 | **Elevated** | **Investigate** — human analyst review |
| 75–100 | **High** | **Escalate** — priority human review |
| 75–100 **and** an imminent-harm category (3.4 active, 3.6, 3.7) **and** human authorization | **Immediate Action** | Human-authorized only; route to the correct unit / victim pathway |

Hard rules:
- The **model may recommend up to "Escalate"**. **"Immediate Action" can only be set by a human.**
- **Low confidence caps the recommendation at "Investigate."**
- Every band ships with its evidence list and the category that drove it.

---

## 5. NOT risk indicators — do-not-flag (blocking rule)

The following must **never, alone or in combination, raise a risk score.** If the model's evidence reduces to any of these, output low risk and note "no lawful risk indicator."

- Religion, caste, ethnicity, region, language, or community
- Political opinion, party affiliation, dissent, or criticism of government/institutions
- Journalism, activism, RTI/whistleblowing, human-rights work
- Gender identity, sexual orientation, or lawful adult relationships
- Lawful protest, satire, parody, or offensive-but-legal speech
- Disability, health status, or economic status
- Legitimate business marketing (genuine sales/urgency with real T&Cs)
- Lawful crowdfunding with a named beneficiary

Reason: these are protected/lawful and are **common false-positive traps** (an activist's fundraiser reads as "financial solicitation + urgency"; a critic reads as "harassment"). Blocking them keeps the tool lawful and accurate.

---

## 6. False-positive handling & review

- **Benign-explanation pass:** before finalizing, the model checks each fired indicator against a plausible lawful explanation and subtracts where one fits.
- **Confidence report:** state which expected fields were missing; thin data → low confidence → cap action.
- **Human review queue:** everything ≥ Elevated enters human review; nothing auto-acts.
- **Audit trail:** store inputs used, indicators fired, weights, benign-pass results, final score, model version, timestamp, and (on confirmation) the analyst's name and case reference. Make it reversible and challengeable.
- **Retention limits:** purge assessed data when the authorized purpose ends.

---

## 7. Output contract (for the backend)

The model must return **only** this JSON, no prose:

```json
{
  "risk_score": 0,
  "risk_band": "Minimal | Low-Moderate | Elevated | High",
  "primary_category": "scam_fraud | bot_fake | harassment_stalking | sextortion_ncii | impersonation | child_safety | credible_threat | illicit_sale | none",
  "category_scores": {
    "scam_fraud": 0,
    "bot_fake": 0,
    "harassment_stalking": 0,
    "sextortion_ncii": 0,
    "impersonation": 0,
    "child_safety": 0,
    "credible_threat": 0,
    "illicit_sale": 0
  },
  "confidence": 0,
  "data_completeness": 0,
  "evidence": [
    { "category": "scam_fraud", "indicator": "UPI solicitation to strangers", "field": "bio", "weight": 25 }
  ],
  "benign_explanations_considered": [
    { "indicator": "urgency language", "benign_fit": "registered-business sale", "subtracted": true }
  ],
  "protected_flag_triggered": false,
  "recommended_action": "Monitor | Investigate | Escalate",
  "requires_human_review": true,
  "notes": ""
}
```

Rules the code enforces on top of the model:
- `recommended_action` never exceeds `Escalate` from the model; `Immediate Action` is a separate human-set field.
- If `protected_flag_triggered` is true and no independent lawful indicator exists → force `risk_band = "Minimal"`.
- If `confidence < threshold` → cap `recommended_action` at `Investigate`.
- Child-safety hits → force human escalation regardless of numeric score.

---

## 8. System prompt (improved)

```
You are a risk-assessment assistant supporting authorized Indian law-enforcement
OSINT analysis. You score a social-media profile for risk indicators and output
a lead for a human analyst — never a verdict.

Rules:
- Assess ONLY the risk categories and indicators defined in the rule book.
- NEVER treat religion, caste, region, language, gender, sexual orientation,
  political opinion, dissent, journalism, or activism as risk indicators. If the
  only "evidence" reduces to these, return minimal risk.
- For each fired indicator, first consider a plausible lawful explanation and
  subtract where one fits.
- Report confidence and data completeness separately from risk. Thin data means
  low confidence, not high risk.
- The credible-threat category fires ONLY on a specific, credible call to
  imminent violence — not on ideology, opinion, or offensive-but-lawful speech.
- Any child-safety indicator: flag and route; do not investigate further or
  reproduce any illicit content.
- Output ONLY the JSON schema provided. No prose, no markdown.

Profile data:
{profile_data}
```

---

## Appendix A — India scam-typology reference patterns

The model matches these behavioral/language patterns (indicative, not exhaustive):

- **Digital-arrest / fake official:** impersonates police/CBI/ED/TRAI/customs; claims the user's Aadhaar/number/parcel is linked to a crime; demands a video call, isolation, and payment to "avoid arrest."
- **UPI / QR reversal:** offers to "send" money but shares a *collect/pay* request or a QR that debits the victim.
- **Instant-loan-app abuse:** pushes quick loans; later signals harassment, contact-list access, morphed-photo threats for recovery.
- **Task / part-time job:** WhatsApp/Telegram recruiting for "like & earn" / "hotel rating" tasks; small early payouts, then blocked withdrawals requiring "deposits."
- **Investment / tip group:** "SEBI-registered" claims, guaranteed returns, Telegram pump groups, fake trading-app screenshots.
- **KYC / OTP / bank:** "your account/SIM/KYC will be blocked — verify now"; solicits OTP or a form on a look-alike domain.
- **OLX / army-officer:** poses as posted military personnel selling furniture/vehicle; uses fake ID card; insists on advance UPI.
- **Parcel / customs (courier):** "your parcel contains drugs/contraband"; hands off to a fake officer; demands a clearance fee.
- **Lottery / prize / KBC:** claims a large win; asks for "processing/GST" fees.
- **Matrimonial / romance:** fast intimacy, foreign-gift/customs-fee story, or crypto-investment pivot.
- **Sextortion:** rapid friend request → intimate video call → recorded → blackmail (see 3.4).
- **Fake customer care:** SEO/social-planted "helpline" numbers for banks/telecoms/e-commerce that phish or push remote-access apps.
- **Utility disconnection:** SMS/DM "electricity/gas will be cut tonight — call this number."

---

*This document governs how the tool reasons about risk. Lawful authorization, scope limits, human oversight, and the protected-category block in Section 5 are prerequisites of operation, not optional add-ons.*
