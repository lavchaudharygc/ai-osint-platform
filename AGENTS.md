# AGENTS.md

## Primary Workspace: Beta-v2

**`D:\HQ-project\Beta-v2` is the active codebase** — "UP Police Cyber Cell OSINT Platform (Beta-v2 SOC)", a leaner full-pipeline OSINT engine. The root `backend/` + `frontend/` at `HQ-project/` is an older, quota-aware variant (see below).

### Beta-v2 Layout

```text
Beta-v2/
|-- backend/
|   |-- app/
|   |   |-- main.py                 FastAPI app (single router)
|   |   |-- config.py               Settings (env-loaded)
|   |   |-- api/investigation.py    full pipeline endpoint
|   |   |-- schemas/investigation.py
|   |   |-- services/               WMN, Instagram, SignalHire, Facebook, TikTok,
|   |   |                           email verifier, associated accounts, Telegram,
|   |   |                           dorking, HiTek, AI analyzer, Twitter
|   |   `-- data/wmn-data.json      WhatsMyName probe data
|-- frontend/                       static UI (port 3000)
|-- run.py / start.ps1 / start.bat  launchers
```

### Beta-v2 Commands

- Start both servers + open browser: `python run.py` (backend on `http://127.0.0.1:8010`, frontend on `http://127.0.0.1:3000`) or `start.ps1`.
- Backend alone: `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010` (from `Beta-v2/backend`).
- `.env` is loaded directly from `Beta-v2/backend/.env`. Beta-v2 is completely self-contained with its own services, config, and requirements.

### Beta-v2 Pipeline (in `backend/app/api/investigation.py`)

`POST /api/v1/investigation/username` runs: input classification (`email`/`phone`/`domain`/`name`/`username`) → WMN probe → concurrent platform scrapers (Instagram, SignalHire, Facebook, TikTok, Twitter, etc.) → email verification → Telegram CTI → dorking → HiTek → AI analysis (Groq primary, Gemini/DeepSeek) → consolidated identity + AI personality synthesis. Network I/O runs in parallel via `asyncio.gather`. Per-step failures are swallowed by `_safe()` and returned as `None`, not fatal.

### Beta-v2 Key Details

- IDs: `UPP-<8 hex>`. Response model in `backend/app/schemas/investigation.py` (`ConsolidatedIdentity`, `AiPersonality`).
- AI models in `config.py`: Groq (`llama-3.3-70b-versatile`), Gemini (`gemini-3.6-flash`), DeepSeek (`deepseek-chat`).
- Diagnostic endpoint: `GET /api/v1/investigation/diagnostics/keys` shows which provider keys are configured.
- Frontend: `frontend/index.html` + `frontend/js/app.js` (+ `lea_pdf_exporter.js`); demo data in `frontend/demo_data.json`.

---

## Legacy Root App (HQ-project/)

AI-OSINT Investigation Engine — a FastAPI backend plus static browser UI for authorized public-data investigations: cross-platform username discovery, exact-full-name person search, identity-correlation support, and evidence-oriented reporting.

Architecture is **quota-aware**: every external capability has exactly one approved provider, automatic cross-provider fallback is disabled, investigations are cached, and paid-provider work is bounded per request.

## Repository Layout

```text
HQ-project/
|-- backend/
|   |-- backend/
|   |   |-- main.py                 FastAPI app entry point
|   |   |-- api/endpoints/          route modules (investigation, apify, providers,
|   |   |                           person_search_routes, reports, training)
|   |   |-- core/                   config.py (Settings), dependencies, events
|   |   |-- schemas/                request/response Pydantic models
|   |   |-- database/               SQLAlchemy ORM, migrations
|   |   |-- services/               provider adapters, analysis services, person_search/
|   |   |   |                       intelligence/, report/
|   |   |-- scripts/                maintenance scripts
|   |-- docs/                       backend integration notes
|   |-- tests/                      35 pytest files (mocked transports)
|   |-- .env.example                copy-only config template
|   |-- requirements.txt
|-- frontend/                       static HTML/JS UI (no build step)
|-- docs/                           project data and research artifacts
|-- ai/                             generated investigation report HTML
|-- start_servers.py                local backend (8010) + frontend (5500) launcher
```

## Commands

All commands run from `backend/` unless noted. PowerShell environment.

- Run backend: `python -m backend.main` (or `uvicorn backend.main:app --reload --host 127.0.0.1 --port 8010`)
- Run full stack: `python start_servers.py` from repo root (backend `http://127.0.0.1:8010`, frontend `http://127.0.0.1:5500`)
- Run tests: `python -m pytest`
- Config: `backend/.env` (copy `backend/.env.example`; never commit real secrets)

Backend has a venv at `backend/.venv`. Ports: backend default 8010 (`.env.example`), code default 8000.

## Architecture Rules (do not break these)

- **One provider per capability, no automatic fallback.** A SerpAPI failure must not call Bright Data or Apify. A social-provider failure returns structured status data. Routing map:
  - Google search/dorking → SerpAPI
  - General web scraping → Bright Data Web Unlocker
  - Instagram/X/LinkedIn/Reddit-posts/Facebook/TikTok → Apify Actors (explicit assignments, e.g. X profile = `scraper_one/x-profile-posts-scraper`, replies/About enrichment = `apidojo/twitter-profile-scraper`)
  - Reddit account metadata → Reddit OAuth Data API
  - Telegram → public `t.me`, optional read-only MTProto
  - YouTube → YouTube Data API v3
  - GitHub → REST + GraphQL
  - Email → Hunter.io
  - Phone → Twilio Lookup
  - Structured extraction → Firecrawl
- **Quota protection.** Budgets in `core/config.py` (`INVESTIGATION_*`, `PERSON_SEARCH_*`). Requests may only *lower* ceilings (`provider_call_limit`, `dork_query_limit`, `cache_mode`). Never launch an unconditional all-platform Actor fan-out; at most 4 paid social platforms by default.
- **Identity correlation is deterministic and local.** It never calls DeepSeek/Groq. Only the optional AI risk review may consume one reserved budget unit; without budget it is evidence-constrained and makes no network call.
- Same username across platforms = evidence **candidate**, not identity proof. Never claim identity confirmation without collector-confirmed output and human review.

## Conventions

- Python 3.10+; type hints everywhere; module docstrings in `"""..."""` style; no untyped public functions.
- Settings live in `backend/core/config.py` via pydantic-settings, validated from `backend/.env` (aliases match env var names). Add new provider settings there with a documented alias and bounds.
- Provider adapters live in `backend/services/` and use mocked HTTP (`httpx`) in tests — never spend external quota in tests.
- Capability routing and routing status come from `backend/services/investigation_policy.py`; `GET /api/v1/providers/status` exposes routing booleans without credentials.
- New services should be constructed with `settings` (the module-level cached instance) and follow the existing adapter shape in sibling files.
- Backend endpoints: `backend/api/endpoints/`, router prefix `/api/v1/...`, Pydantic schemas in `backend/schemas/`.
- Frontend is static JS (no bundler). `data_mappers.js` maps API responses; UI tests are `.cjs` files in `frontend/tests/` (run with `node`).

## Security / Safety

- Never include `str(exc)` in error responses (see `unhandled_exception_handler` in `backend/main.py`) — it can leak internal paths. Log server-side instead.
- `.env` and any secrets are gitignored; never commit provider keys, sessions (`*.session`), or DB dumps.
- Investigation history persistence (SQLite) is default-off and stores plaintext responses; keep out of source control.
- API defaults to loopback (`127.0.0.1`). Provider-spending routes have no user auth — keep behind a trusted gateway.
- This tool is for lawful, authorized investigations of public data only.
