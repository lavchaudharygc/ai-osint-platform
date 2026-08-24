# Beta-v2 OSINT Platform

Beta-v2 contains a FastAPI backend on port `8010` and a static frontend on port
`3000`. Python 3.11 or newer is required. The frontend has no npm/build step.

## First-time Windows setup

Run these commands in PowerShell:

```powershell
cd D:\projects\public-osint\Beta-v2
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

Create the local configuration only if it does not already exist:

```powershell
if (-not (Test-Path .\backend\.env)) {
    Copy-Item .\backend\.env.example .\backend\.env
}
notepad .\backend\.env
```

Keep unused provider keys empty. Never commit `backend/.env`.

## Configure authentication and audit

Recommended: generate and atomically store both distinct secrets without
printing them:

```powershell
.\.venv\Scripts\python.exe .\backend\scripts\configure_security.py
```

The command is idempotent. It refuses to replace invalid keys after a non-empty
audit chain exists, because rotating the audit key would make that chain
unverifiable.

Manual alternative: generate two different local secrets:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48)); print(secrets.token_urlsafe(48))"
```

Put the first output and the different second output in `backend/.env`:

```dotenv
AUTH_SESSION_SECRET=<first generated value>
AUDIT_HMAC_KEY=<second generated value>
AUTH_COOKIE_SECURE=false
```

`AUTH_COOKIE_SECURE=false` is only for the loopback HTTP development URLs. Set it
to `true` when the application is served through HTTPS.

Provision an analyst. The command prompts for the password so it does not appear
in shell history:

```powershell
.\.venv\Scripts\python.exe .\backend\scripts\create_soc_user.py --username analyst --role investigator --role breach_pii_viewer
```

- `investigator` permits the email investigation request.
- `breach_pii_viewer` additionally exposes the opt-in restricted contact-record
  control. Both roles are required to request those records.
- There are no built-in usernames or passwords.
- To rotate an existing analyst password or roles, repeat the command with
  `--replace`.

Sessions are short-lived, signed, HttpOnly, SameSite=Strict cookies. A restricted
provider access attempt is durably audited before collection, and disclosure
fails closed unless a second field-aware audit record is written. Runtime users
and audit files live under `backend/runtime/` and are ignored by Git.

Verify the audit chain at any time:

```powershell
.\.venv\Scripts\python.exe .\backend\scripts\verify_audit.py
```

## Email investigation providers

The local validation and DNS sections work without paid keys. Provider-dependent
sections return `not_configured` or `disabled` until their dedicated provider is
enabled. Existing unrelated scraper keys are not automatic fallbacks.

For the exact-email LeakOSINT lookup and restricted contact records:

```dotenv
EMAIL_INVESTIGATION_BREACH_ENABLED=true
EMAIL_INVESTIGATION_BREACH_API_KEY=<complete LeakOSINT token>
```

For bounded Google/Bing discovery through SerpAPI:

```dotenv
SERPAPI_KEY=<complete SerpAPI key>
EMAIL_INVESTIGATION_DORK_ENABLED=true
```

These entries are optional only if you do not want those provider-backed sections.
They are required for those sections to return data. The server permits at most
three query templates, six provider calls, and the configured result ceiling; a
request can only lower those limits.

Older Beta-v2 revisions contained embedded provider-key fallbacks. They have been
removed. Revoke and replace any live provider credential that matched a committed
fallback, then keep the replacement only in `backend/.env`.

## People Search provider

The standalone **People Search** view performs bounded exact-full-name discovery
across selected public social platforms. It uses SerpAPI only and never falls
back to another provider or launches the full Target Scan pipeline.

Configure the existing search credential in `backend/.env`:

```dotenv
SERPAPI_KEY=<complete SerpAPI key>
PERSON_SEARCH_ENABLED=true
```

Optional server-owned ceilings are documented in `backend/.env.example`. The
browser can lower the candidate count, but cannot raise the query, result, or
timeout ceilings. Returned profiles, usernames, and images are unverified leads;
the workflow performs no contact, breach, background-check, or AI enrichment.

## Run both servers

```powershell
cd D:\projects\public-osint\Beta-v2
.\.venv\Scripts\python.exe .\run.py
```

Open:

- Frontend: `http://127.0.0.1:3000/`
- API health: `http://127.0.0.1:8010/health`
- Protected-workflow readiness: `http://127.0.0.1:8010/ready`
- Swagger: `http://127.0.0.1:8010/docs`

Sign in with the provisioned analyst. Select **People Search** for exact-name
public-profile discovery, or **Email Intel** for the governed email workflow.
For People Search, enter the exact full name, optionally add a state/location,
organization, and two-letter country code, select the platforms, then run the
search. Each platform initially shows five candidates; **Show more profiles**
expands the already-returned rows inline and **Show less** collapses them without
another provider call.

For Email Intel, complete the case/reason/authorization fields and explicitly
select **Restricted breach contact records** when the case requires that view.
Stop both servers with `Ctrl+C`. The supplied launchers suppress backend access
logs so signed upstream image URLs are not written to the console; security audit
events are still written to the HMAC-chained audit file. The launcher reports
success only after the backend confirms that the session secret, an active user
store, and the audit key/chain are ready, and after the frontend answers its HTTP
check.

If the launcher reports that port `3000` or `8010` is already in use, do not start
a second copy. Find the existing listener and stop it from the terminal that
started it:

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 3000,8010 | Select-Object LocalAddress,LocalPort,OwningProcess
```

## Restricted disclosure boundary

The gated dashboard can display provider-attributed email, full name, phone,
address, city, state, district, postal code, country, username, company, and job
title. Values are investigative leads and require human verification.

Passwords, hashes, tokens, cookies, authentication secrets, payment data,
government identifiers, medical data, dates of birth, IP addresses, and device
identifiers remain suppressed. Unknown provider fields are not rendered. The
browser's CSV, TXT, and JSON exports intentionally exclude restricted values.

## Email API request

`POST /api/v1/email-investigation` requires an authenticated `investigator`
session, the session CSRF header, one validated email, and explicit case
attestation. Restricted records additionally require `breach_pii_viewer` and an
audit write:

```json
{
  "email": "subject@example.com",
  "authorized": true,
  "reason_code": "active_investigation",
  "case_id": "UPP-CASE-2026-001",
  "include_gravatar": true,
  "include_breach_lookup": true,
  "include_restricted_breach_details": true,
  "include_web_discovery": true,
  "dork_query_limit": 3
}
```

## People Search API request

`POST /api/v1/person-search` requires an authenticated `investigator` session
and the session CSRF header. `GET /api/v1/person-search/status` reports readiness
and non-secret server ceilings.

```json
{
  "full_name": "Shubham Jha",
  "location": "Lucknow, Uttar Pradesh",
  "country_code": "IN",
  "platforms": ["instagram", "twitter", "facebook", "linkedin"],
  "max_profiles": 20
}
```

## Tests

All provider transports are mocked; the tests spend no provider quota:

```powershell
cd D:\projects\public-osint\Beta-v2
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt
Set-Location .\backend
..\.venv\Scripts\python.exe -m pytest -q
Set-Location ..
node .\frontend\tests\auth_ui.test.cjs
node .\frontend\tests\email_investigation_ui.test.cjs
node .\frontend\tests\image_proxy_ui.test.cjs
node .\frontend\tests\legacy_render_security.test.cjs
node .\frontend\tests\legacy_scan_lifecycle.test.cjs
node .\frontend\tests\people_search_ui.test.cjs
node .\frontend\tests\phone_investigation_ui.test.cjs
```

## Deployment boundary

The built-in account store and audit chain are suitable for the current
single-host SOC deployment. A multi-host deployment should place the backend
behind TLS and a centralized identity, authorization, audit-retention, and rate
limiting layer. Bulk monitoring, persistent case history, screenshots,
reverse-image search, and recursive crawling remain outside this module.
