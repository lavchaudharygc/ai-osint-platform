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

The loopback deployment includes the requested operator account `uppolice` with
password `test`. It receives both protected-workflow roles, including Person
Search access. For a different deployment, provision an additional analyst; the
command prompts for the password so it does not appear in shell history:

```powershell
.\.venv\Scripts\python.exe .\backend\scripts\create_soc_user.py --username analyst --role investigator --role breach_pii_viewer
```

- `investigator` permits the email investigation request.
- `breach_pii_viewer` additionally exposes the opt-in restricted contact-record
  control. Both roles are required to request those records.
- `uppolice` / `test` can be replaced with `AUTH_USER` / `AUTH_PASSWORD` in
  `backend/.env`.
- To rotate an existing analyst password or roles, repeat the command with
  `--replace`.

Sessions use signed, HttpOnly, SameSite=Strict cookies. The dashboard renews a
valid session in place while it remains open, so investigations do not trigger
an automatic logout; explicit logout still clears the browser session. Renewed
sessions are credential-bound, so changing the account password invalidates old
cookies. A restricted provider access attempt is durably audited before
collection, and disclosure fails closed unless a second field-aware audit
record is written. Runtime users and audit files live under `backend/runtime/`
and are ignored by Git.

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

## Apify social scrapers and account quota

Instagram, TikTok, public Facebook Pages, X timelines, and LinkedIn use the same
asynchronous Actor client. Before a paid Actor is
started, the backend makes one read-only `/users/me/limits` request and caches
the result for five minutes. If monthly usage is at the account limit, every
paid launch is skipped and diagnostics report `quota_exhausted`; the app resumes
automatically after the usage cycle resets or the account owner raises the
limit. A launch also has a default `$1.00` maximum-charge ceiling.

Configure the token and review the non-secret ceilings in `backend/.env.example`:

```dotenv
APIFY_API_TOKEN=<complete Apify API token>
APIFY_QUOTA_CHECK_TTL_SECONDS=300
APIFY_QUOTA_CHECK_TIMEOUT_SECONDS=10
APIFY_MAX_TOTAL_CHARGE_USD_PER_RUN=1.0
APIFY_LINKEDIN_POSTS_LIMIT=15
```

The dashboard integration badge performs the same read-only capacity check.
`Ready` means the token can read its account limits and budget remains; it does
not claim that a particular public target will return data. `Quota exhausted`
requires action in Apify Console under **Billing / Limits** or waiting for the
displayed cycle end. `Access denied` requires an API token with Actor Run rights
and, where applicable, one-time Actor permission/subscription approval. Never
put the token in Git or browser code.

Actor IDs are explicit `APIFY_*_ACTOR_ID` settings. The X default is a real
profile/timeline collector (`automation-lab/twitter-scraper`); follower records
are no longer relabelled as tweets. Facebook collection is intentionally
described as public Page collection because the configured Actors do not promise
personal-profile access.

For a username Target Scan, LinkedIn post collection starts only after the
profile collector confirms a public `linkedin.com/in/...` URL. It uses the same
request-scoped Apify client, starts at most one posts Actor, and returns at most
`APIFY_LINKEDIN_POSTS_LIMIT` rows (15 by default, with a hard maximum of 20).
Only rows whose public author URL matches the confirmed profile are attached to
the dossier. A skipped, empty, or failed post search is reported separately as
`provider_statuses.linkedin_posts` and never removes a successful profile.
Operational logging records only status and counts under
`event=linkedin_posts_completed`, never the search value or post content.

Google dorking uses SerpAPI only. It never launches an Apify Actor or switches
to another provider when SerpAPI is missing, exhausted, or unavailable.

## Dedicated GitHub and YouTube collectors

Username Target Scan includes two independent, bounded collectors that do not
depend on Google dorking or Apify:

- GitHub uses the official public REST API for one profile, one page of public
  repositories, and one page of recent public activity. It works anonymously
  by default. `GITHUB_API_TOKEN` is optional and only provides authenticated
  rate limits; if used, keep a read-only token in the recipient's own
  `backend/.env`. When a token is present, follower/following counts are
  conservatively suppressed because GitHub may reveal hidden counts to the
  token owner; only fields with a public-data contract are retained.
- YouTube uses the official YouTube Data API v3 for an exact channel handle,
  its uploads playlist, and one batched video-details request. It requires a
  locally configured `YOUTUBE_API_KEY`; enable YouTube Data API v3 for that key
  and restrict it to the backend deployment where practical.

```dotenv
GITHUB_ENABLED=true
GITHUB_API_TOKEN=
GITHUB_MAX_REQUESTS_PER_SCAN=3
GITHUB_MAX_REPOSITORIES=10
GITHUB_MAX_EVENTS=10

YOUTUBE_ENABLED=true
YOUTUBE_API_KEY=<recipient's own API key>
YOUTUBE_MAX_REQUESTS_PER_SCAN=3
YOUTUBE_VIDEOS_LIMIT=10
```

The server hard-caps both collectors at three HTTP calls per username scan and
never retries, paginates, or falls back to a different provider. Non-username
targets make zero GitHub and YouTube calls. A failure remains isolated and is
reported in `provider_statuses.github` or `provider_statuses.youtube`; a
successful collector still appears when the other one fails. GitHub rate-limit
metadata and YouTube quota units used are shown in diagnostics without exposing
credentials. Count-only operational summaries use
`event=target_collector_summary` and never log the searched handle or collected
content.

## Target Scan Google dorking

Target Scan now prepares five target-type-aware Google searches for usernames,
names, email addresses, phone numbers, or domains. Each query keeps the target
bound to its `OR` clauses and covers a different evidence category: exact web
mentions, professional/code profiles, social/community profiles, contact or
directory references, and public documents. A single SerpAPI call requests up
to ten organic rows, so the default plan can examine up to 50 raw rows without
pagination or hidden provider calls.

The backend normalizes public HTTP(S) URLs, removes common tracking parameters,
de-duplicates repeated links, and round-robins query buckets before applying the
40-result display ceiling. A quota, authentication, rate-limit, timeout, or
provider error stops further searches immediately; results from earlier
successful queries are retained with `partial` status. The dashboard displays
the provider, successful/attempted query counts, removed duplicates, truncation,
and the real failure state instead of describing every failure as zero hits.

The non-secret server ceilings are documented in `backend/.env.example`:

```dotenv
DORKING_ENABLED=true
DORKING_TIMEOUT_SECONDS=15
DORKING_MAX_QUERIES=5
DORKING_RESULTS_PER_QUERY=10
DORKING_MAX_RESULTS=40
DORKING_COUNTRY_CODE=in
```

Operational logs use `event=dorking_provider_failed` and
`event=dorking_completed`. They contain only provider status and counters, not
the searched value, generated dorks, API key, titles, snippets, or URLs.

## Cross-platform hashtag analysis

Successful Instagram, TikTok, X, public Facebook Page, attributed LinkedIn
posts, YouTube videos, and explicit hashtags in GitHub public content are
normalized into the top-level `hashtag_analysis` response.
The analysis is
deterministic and local: it makes no additional provider or AI call. Tags from
public bios and collected posts/videos are case-normalized, counted once per
source item, ranked, and attributed to their source platforms. The dashboard
shows overall totals, cross-platform tags, per-platform summaries, and the
original dossier-level tag lists. The same normalized summary is placed first
in the behavioral-analysis evidence corpus so every supported platform can
influence classification, not only Instagram.

Operational logs record only the analysis status and counts under
`event=hashtag_analysis_completed`; hashtag values and target identifiers are
not written to the diagnostic log.

## Target Scan CTI privacy and quota policy

Target Scan uses its separate `TELEGRAM_CTI_API_KEY`. Provider responses are
redacted at the CTI service boundary before correlation, AI filtering, browser
rendering, or PDF export. Completed breach responses are never cached. Identical
simultaneous lookups may share only their in-flight work, which is discarded as
soon as it completes.

The committed defaults accept at most three seed identifiers, five logical
searches, six HTTP attempts per investigation, and 30 CTI provider calls in a
rolling hour for the application process. Calls are serialized and paced. A
rate-limit, exhausted-balance, or authentication response stops remaining work
and opens a five-minute circuit-breaker cooldown instead of retrying repeatedly.
All ceilings are documented in `backend/.env.example`.

Indian-centric filtering runs locally by default. Sending already-redacted CTI
records to an external AI requires the explicit, privacy-reviewed opt-in
`CTI_EXTERNAL_AI_FILTERING_ENABLED=true`; the target query itself is not placed
in that AI prompt.

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

## Operational diagnostics

Troubleshooting events are written automatically with UTC timestamps and safe
request IDs. No extra `.env` configuration is required. The two files are:

- `backend/runtime/application.log` — backend startup/readiness, authentication
  and session renewal/rejection reasons, request status/timing, and bounded
  provider outcomes.
- `backend/runtime/launcher.log` — occupied ports, child-process startup/exit,
  readiness timeouts, browser launch, and shutdown.

Both files rotate automatically (`application.log` at 5 MiB with five backups;
`launcher.log` at 2 MiB with three backups), and the entire `runtime` directory
is ignored by Git. Follow the live backend log in PowerShell with:

```powershell
Get-Content .\backend\runtime\application.log -Tail 100 -Wait
```

For launcher failures:

```powershell
Get-Content .\backend\runtime\launcher.log -Tail 100
```

Failed investigation alerts display a safe `X-Request-ID` reference. Find the
matching backend events with (replace the example ID):

```powershell
Select-String -Path .\backend\runtime\application.log* -SimpleMatch "request_id=abc123example"
```

The browser keeps only the latest 100 allowlisted authentication diagnostic
events. In Developer Tools, run `SocAuth.diagnostics()` to inspect them or
`SocAuth.clearDiagnostics()` to remove them. These records contain status and
reason codes only—not usernames, passwords, cookies, CSRF values, targets,
request/response bodies, provider keys, emails, phone numbers, or full URLs.

The operational files are not the compliance audit. The append-only,
HMAC-chained `security_audit.jsonl` remains separate and is never rotated by
this feature. Review diagnostic files before sharing them outside the trusted
SOC environment. Optional `APP_LOG_*` controls are documented in
`backend/.env.example`; keep Uvicorn access logging disabled because raw URLs
can contain sensitive query parameters.

Contact discovery emits count-only operational events. Search for
`event=contact_enrichment_routed` to see which paid resolver was selected and
how many resolver calls were made; search for
`event=contact_discovery_completed` to see observed email/phone counts, email
guess counts, verification provider-call counts, and cache-reuse counts. These rows never include
the email address, phone number, lookup identifier, or provider key.

Target Scan normalizes and de-duplicates contacts from the request, LinkedIn,
Facebook, Instagram, TikTok, X, GitHub, YouTube, SignalHire, and RocketReach
before verification.
Generated email patterns remain separate, explicitly unverified candidates.
Local syntax checks never claim that a mailbox is deliverable. Provider national
phone numbers remain unverified unless a country code is present; only a
user-supplied local phone uses the platform's `IN` default.

The route makes at most one contact-enrichment call: an exact email/phone can use
SignalHire, while a collector-confirmed LinkedIn `/in/` URL can use RocketReach.
Exact contacts are not sent to username-oriented WMN or Apify collectors. The
route skips RocketReach only when the same confirmed LinkedIn profile already
provides both email and phone data; contacts on unrelated same-handle profiles
do not suppress an exact lookup. It never falls through to a second paid
provider after an error.
Bio/about-only contacts remain visible but do not automatically consume
verification or CTI quota. Failed provider envelopes cannot contribute stale
contact values.

With request `cache_mode: "use"` (the dashboard default), successful
SignalHire, RocketReach, Hunter, and ZeroBounce results are reused for a short
TTL (15 minutes by default). The cache is bounded, held only in backend process
memory, keyed by an HMAC fingerprint rather than the raw identifier, and
cleared on restart.
`"refresh"` forces and replaces a lookup; `"bypass"` neither reads nor writes
the cache. CTI/breach responses, full investigation responses, and failed
provider results are never cached. Browser responses remain `no-store`.

Prefix a dotted social handle with `@` (for example, `@john.doe`). Unprefixed
hostname-shaped values are treated as domains so modern or internationalized
domains do not accidentally launch paid username collectors.

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
