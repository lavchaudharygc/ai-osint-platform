# Email Verification Methods for OSINT

## Overview
Methods to verify if guessed email addresses actually exist — WITHOUT sending emails or violating legal compliance (Indian IT Act).

---

## SECTION 1: VERIFICATION SERVICES (NO EMAIL SENDING)

### Service 1: Hunter.io Email Verifier
*   **URL:** `https://hunter.io/email-verifier`
*   **API:** `https://api.hunter.io/v2/email-verifier`
*   **Free Tier:** 25 verifications/month (Ideal for targeted OSINT).
*   **Paid:** Starting $49/month (500 verifications).
*   **Features:** Checks format validity, domain MX records, and mailbox existence (via SMTP handshake) without logging suspicious metadata on the target server.
*   **API Response Format:**
```json
{
  "data": {
    "status": "valid",
    "result": "deliverable",
    "score": 85,
    "email": "contact@gcsislet.com",
    "regexp": true,
    "gibberish": false,
    "disposable": false,
    "webmail": false,
    "mx_records": true,
    "smtp_check": true
  }
}
```

### Service 2: NeverBounce
*   **URL:** `https://neverbounce.com/`
*   **API:** `https://api.neverbounce.com/v4/single/check`
*   **Features:** Real-time verification, Catch-all detection (crucial for corporate domains), Disposable email detection.

### Service 3: ZeroBounce
*   **URL:** `https://www.zerobounce.net/`
*   **API:** `https://api.zerobounce.net/v2/validate`
*   **Free Tier:** 100 verifications/month.
*   **Features:** Email validation, Spam trap detection (prevents LE tools from hitting honey-pots), Abuse email detection.

---

## SECTION 2: MANUAL/STEALTH VERIFICATION METHODS

### Method 1: The Gmail "GX" Cookie Check
A highly stealthy way to check if a `@gmail.com` address is actively registered.
*   **URL:** `https://mail.google.com/mail/gxlu?email={email}`
*   **Response:** If the email exists, Google returns a specific `GX` cookie in the HTTP headers.
```python
import requests

def check_gmail(email):
    url = f"https://mail.google.com/mail/gxlu?email={email}"
    response = requests.get(url, timeout=10)
    return 'GX' in response.cookies
```

### Method 2: Signup Form Enumeration (The "Already Taken" Trick)
*   **Yahoo:** `https://login.yahoo.com/account/create?email={email}`
*   **Outlook/Hotmail:** `https://signup.live.com/`
*   **GitHub:** `https://github.com/signup_check/email?value={email}` (Returns `false` if the email is available, meaning it is NOT attached to a GitHub account).

### Method 3: Breach Database Correlation (HaveIBeenPwned)
If an email appears in a data breach, it 100% exists and actively belongs to a real person.
*   **URL:** `https://haveibeenpwned.com/api/v3/breachedaccount/{email}`
*   **Response:** JSON list of breaches (e.g., "LinkedIn", "Canva") where the email was compromised.

---

## SECTION 3: DOMAIN & MX VERIFICATION SCRIPTING

Before checking the specific user (e.g., `lav@`), always verify the company domain exists and can accept mail.

```python
import socket
import dns.resolver

def check_domain_and_mx(domain):
    # 1. Check if domain resolves to an IP
    try:
        socket.gethostbyname(domain)
    except socket.gaierror:
        return {"valid": False, "reason": "Domain does not exist"}
        
    # 2. Check if domain has Mail Exchange (MX) records
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        return {"valid": True, "mx_servers": [str(x.exchange) for x in mx_records]}
    except dns.resolver.NoAnswer:
        return {"valid": False, "reason": "No MX records found"}
```

---

## SECTION 4: IMPLEMENTATION PRIORITY

| Method | Cost | Accuracy | Speed | Priority Level |
|--------|------|----------|-------|----------------|
| Format validation | Free | Low | Instant | **P0** (always run first) |
| Domain/MX check | Free | Medium | Fast | **P0** (always run second) |
| Hunter.io API | Freemium | High | 2-5 sec | **P1** (Primary automated verification) |
| Have I Been Pwned | Free | Medium | 2-3 sec | **P1** (Check for historical footprint) |
| Gmail cookie check | Free | Medium | 1-2 sec | **P2** (Only for @gmail addresses) |
| Direct SMTP handshake | Free | High | 5-10 sec | **P2** (Use cautiously; risk of IP ban) |

---

## SECTION 5: LEGAL CONSIDERATIONS

✅ **Legal (Always Safe):**
- Checking email format (Regex).
- Verifying domain exists / DNS lookups.
- Checking MX records.
- Using public APIs (Hunter.io, HIBP).
- Google cookie check (Querying public endpoint).

⚠️ **Gray Area (Use with proxy/rate-limits):**
- Direct SMTP handshakes without sending (some corporate firewalls log this as an attack).
- Automated verification at scale.

❌ **Illegal (Do Not Perform):**
- Sending "test" emails to verify (Violates LE OPSEC).
- Attempting to log into email accounts (Violates IT Act Section 66).
- Phishing/sending tracking pixels to force verification.

---

## SECTION 6: PRACTICAL TRAINING EXAMPLES

### Example 1: Verifying a Corporate Domain (gcsislet.com)
**Target:** `contact@gcsislet.com`
1. **Domain/MX Check:** The script runs `check_domain_and_mx('gcsislet.com')`. It successfully returns MX servers (e.g., `mail.gcsislet.com`).
2. **Hunter.io Check:** The API is queried. It returns a score of `85`, `smtp_check: true`, and `webmail: false` (proving it is a corporate domain, not a generic provider).
3. **Conclusion:** Email confidently verified as the official corporate contact.

### Example 2: Correlating a Breached Gmail (shubhamcyberexpert)
**Target:** Guessed email `shubhamcyberexpert@gmail.com`
1. **Gmail GX Cookie Check:** The script queries `mail.google.com/mail/gxlu` and successfully extracts the `GX` cookie, proving the account is actively registered.
2. **HaveIBeenPwned (HIBP) Check:** The script queries HIBP and finds this email was present in the 2021 Canva data breach. 
3. **Conclusion:** This proves not only that the email exists, but that it has a long-standing historical footprint belonging to a real person. 

### Example 3: Ruling out a False Positive (arkagrawall)
**Target:** Guessed email `ark.agrawal@company.in`
1. **Domain/MX Check:** Domain exists, but `dns.resolver` returns `No MX records found`.
2. **Conclusion:** The domain does not have mail servers configured. It is impossible for `ark.agrawal@company.in` to exist. The script instantly drops this guess and moves to the next permutation, saving API credits.
