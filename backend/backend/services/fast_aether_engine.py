"""Fast Aether Engine high-speed parallel intelligence orchestrator."""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from backend.core.config import settings
from backend.services.wmn_service import WhatsMyNameService
from backend.services.github_service import GitHubService
from backend.services.hunter_service import HunterService
from backend.services.twilio_lookup_service import TwilioLookupService
from backend.services.google_dorking import GoogleDorkingService
from backend.services.telegram_cti_service import get_cti_service
from backend.services.signalhire_service import SignalHireService
from backend.services.ai_analyzer import AIAnalyzer

logger = logging.getLogger(__name__)


class FastAetherEngine:
    """High-speed parallel OSINT investigator combining WhatsMyName 700+ site scanner,
    Apify Instagram/Twitter scrapers, GitHub API, Hunter.io, Twilio, SignalHire, LeakOSINT breach data, and AI personality.
    """

    def __init__(self):
        self.wmn_service = WhatsMyNameService(concurrency=40, timeout_seconds=6.0)
        self.github_service = GitHubService()
        self.hunter_service = HunterService()
        self.twilio_service = TwilioLookupService()
        self.google_dorking = GoogleDorkingService()
        self.cti_service = get_cti_service()
        self.signalhire_service = SignalHireService()
        self.ai_analyzer = AIAnalyzer()

    async def _apify_run_sync(self, actor_id: str, payload: dict) -> list:
        token = getattr(settings, "apify_api_token", None)
        if not token:
            return []
        url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={token}&timeout=30"
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code in (200, 201):
                    data = res.json()
                    return data if isinstance(data, list) else [data]
                return []
        except Exception as exc:
            logger.warning("Apify %s call failed: %s", actor_id, exc)
            return []

    def _classify_input(self, raw: str) -> str:
        s = raw.strip()
        if "@" in s and "." in s:
            return "email"
        if s.startswith("+") or (s.replace(" ", "").replace("-", "").isdigit() and len(s) >= 7):
            return "phone"
        if "." in s and not " " in s:
            return "domain"
        if " " in s:
            return "name"
        return "username"

    async def execute_investigation(
        self, query: str, entity_type: str = "auto", platforms: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        t0 = time.time()
        started_at = datetime.now(timezone.utc).isoformat()
        clean_query = query.strip().lstrip("@")
        kind = self._classify_input(clean_query) if entity_type == "auto" else entity_type

        provider_logs: List[Dict[str, Any]] = []

        # Define parallel async tasks
        async def run_wmn():
            t_start = time.time()
            try:
                res = await self.wmn_service.scan_handle(clean_query)
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append(
                    {"provider": "whatsmyname", "status": "ok", "ms": ms, "message": f"Scanned {res['scanned']} sites, found {res['found_count']}"}
                )
                return res
            except Exception as exc:
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "whatsmyname", "status": "error", "ms": ms, "message": str(exc)})
                return {"scanned": 0, "found_count": 0, "hits": [], "duration_ms": ms}

        async def run_instagram():
            if kind not in ("username", "name"):
                return None
            t_start = time.time()
            try:
                items = await self._apify_run_sync("apify~instagram-profile-scraper", {"usernames": [clean_query]})
                p = items[0] if items and isinstance(items[0], dict) else None
                ms = int((time.time() - t_start) * 1000)
                status = "ok" if p else "empty"
                provider_logs.append({"provider": "instagram", "status": status, "ms": ms})
                if not p:
                    return None
                return {
                    "handle": p.get("username") or clean_query,
                    "fullName": p.get("fullName"),
                    "bio": p.get("biography"),
                    "avatarUrl": p.get("profilePicUrl") or p.get("profilePicUrlHD"),
                    "followers": p.get("followersCount"),
                    "following": p.get("followsCount"),
                    "posts": p.get("postsCount"),
                    "verified": bool(p.get("verified")),
                    "url": p.get("url") or f"https://instagram.com/{clean_query}",
                }
            except Exception as exc:
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "instagram", "status": "error", "ms": ms, "message": str(exc)})
                return None

        async def run_github():
            if kind not in ("username", "name"):
                return None
            t_start = time.time()
            try:
                res = await self.github_service.get_profile(clean_query)
                ms = int((time.time() - t_start) * 1000)
                status = "ok" if res and not res.get("error") else "empty"
                provider_logs.append({"provider": "github", "status": status, "ms": ms, "message": "GitHub profile fetched"})
                return res
            except Exception as exc:
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "github", "status": "error", "ms": ms, "message": str(exc)})
                return None

        async def run_hunter():
            if kind not in ("email", "domain", "username"):
                return None
            t_start = time.time()
            try:
                res = await self.hunter_service.verify_email(clean_query) if kind == "email" else None
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "hunter", "status": "ok" if res else "empty", "ms": ms})
                return res
            except Exception as exc:
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "hunter", "status": "error", "ms": ms, "message": str(exc)})
                return None

        async def run_twilio():
            if kind != "phone":
                return None
            t_start = time.time()
            try:
                res = await self.twilio_service.lookup(clean_query)
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "twilio", "status": "ok" if res else "empty", "ms": ms})
                return res
            except Exception as exc:
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "twilio", "status": "error", "ms": ms, "message": str(exc)})
                return None

        async def run_dorks():
            t_start = time.time()
            try:
                res = await self.google_dorking.search_username(clean_query)
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "serpapi", "status": "ok" if res else "empty", "ms": ms})
                return res
            except Exception as exc:
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "serpapi", "status": "error", "ms": ms, "message": str(exc)})
                return {}

        async def run_cti():
            t_start = time.time()
            try:
                res = await self.cti_service.search(clean_query)
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "leakosint_cti", "status": "ok" if res else "empty", "ms": ms})
                return res.model_dump() if hasattr(res, "model_dump") else res
            except Exception as exc:
                ms = int((time.time() - t_start) * 1000)
                provider_logs.append({"provider": "leakosint_cti", "status": "error", "ms": ms, "message": str(exc)})
                return None

        # Execute primary tasks concurrently
        wmn_res, instagram_res, github_res, hunter_res, twilio_res, dorks_res, cti_res = await asyncio.gather(
            run_wmn(), run_instagram(), run_github(), run_hunter(), run_twilio(), run_dorks(), run_cti()
        )

        # Check for LinkedIn URL in dorks or hits for SignalHire enrichment
        linkedin_url = None
        dork_hits = []
        if isinstance(dorks_res, dict):
            dork_hits = dorks_res.get("results") or dorks_res.get("hits") or []
            for dork in dork_hits:
                url = dork.get("url") or dork.get("link") or ""
                if "linkedin.com/in/" in url:
                    linkedin_url = url
                    break

        signalhire_res = None
        if linkedin_url:
            try:
                signalhire_res = await self.signalhire_service.search_candidate(linkedin_url)
            except Exception as exc:
                logger.warning("SignalHire lookup error: %s", exc)

        # AI Personality & Risk Analysis based on collected corpus
        corpus_parts = []
        if github_res and isinstance(github_res, dict) and not github_res.get("error"):
            bio = github_res.get("bio") or github_res.get("company") or ""
            if bio:
                corpus_parts.append(f"[GitHub] {bio}")
        if wmn_res and isinstance(wmn_res, dict):
            hits = wmn_res.get("hits", [])
            for h in hits[:10]:
                corpus_parts.append(f"[{h.get('category')}] Account exists on {h.get('site')} ({h.get('url')})")
        if isinstance(dork_hits, list):
            for d in dork_hits[:5]:
                corpus_parts.append(f"[Dork] {d.get('title', '')} - {d.get('snippet', '')}")

        corpus_text = "\n".join(corpus_parts)

        # AI Analysis
        ai_analysis = await self._run_ai_personality_analysis(
            query=clean_query,
            github_res=github_res,
            dorks_res=dork_hits,
            corpus_text=corpus_text,
        )

        # Build Consolidated Identity & Scraped Data for UI DataMappers
        found_hits = wmn_res.get("hits", []) if isinstance(wmn_res, dict) else []
        social_profiles = {}
        cross_platform_matches = []
        scraped_data = {}

        for hit in found_hits:
            site_name = hit["site"]
            site_key = site_name.lower().replace(" ", "_").replace(".", "_")
            url = hit["url"]
            social_profiles[site_key] = {
                "platform": site_name,
                "category": hit["category"],
                "url": url,
                "username": clean_query,
            }
            cross_platform_matches.append({
                "platform": site_name,
                "exists": True,
                "url": url,
                "confidence": 0.9,
                "scraper_confirmed": True,
                "sources": ["whatsmyname"],
            })
            scraped_data[site_key] = {
                "platform": site_name,
                "url": url,
                "username": clean_query,
                "status": "found",
                "category": hit.get("category", "general"),
                "profile_url": url,
            }

        if instagram_res and isinstance(instagram_res, dict):
            social_profiles["instagram"] = instagram_res
            cross_platform_matches.append({
                "platform": "Instagram",
                "exists": True,
                "url": instagram_res.get("url"),
                "confidence": 0.95,
                "scraper_confirmed": True,
                "sources": ["apify_instagram"],
            })
            scraped_data["instagram"] = instagram_res

        if github_res and isinstance(github_res, dict) and not github_res.get("error"):
            social_profiles["github"] = {
                "platform": "GitHub",
                "username": github_res.get("login") or clean_query,
                "url": github_res.get("html_url") or f"https://github.com/{clean_query}",
                "fullName": github_res.get("name"),
                "bio": github_res.get("bio"),
                "followers": github_res.get("followers"),
                "avatarUrl": github_res.get("avatar_url"),
            }
            cross_platform_matches.append({
                "platform": "GitHub",
                "exists": True,
                "url": github_res.get("html_url") or f"https://github.com/{clean_query}",
                "confidence": 0.95,
                "scraper_confirmed": True,
                "sources": ["github_api"],
            })
            scraped_data["github"] = github_res

        duration_total_ms = int((time.time() - t0) * 1000)
        finished_at = datetime.now(timezone.utc).isoformat()

        return {
            "engine_mode": "fast_aether",
            "query": clean_query,
            "entityType": entity_type,
            "kind": kind,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "durationMs": duration_total_ms,
            "wmn_summary": {
                "scanned": wmn_res.get("scanned", 0) if isinstance(wmn_res, dict) else 0,
                "found_count": wmn_res.get("found_count", 0) if isinstance(wmn_res, dict) else 0,
                "hits": found_hits,
            },
            "socialProfiles": social_profiles,
            "cross_platform_matches": cross_platform_matches,
            "scraped_data": scraped_data,
            "github": github_res,
            "hunter": hunter_res,
            "twilio": twilio_res,
            "googleDorking": {"query": clean_query, "hits": dork_hits},
            "cti": cti_res,
            "signalhire": signalhire_res,
            "aiPersonality": ai_analysis,
            "providerLog": provider_logs,
            "sourcesTotal": len(provider_logs),
            "sourcesEmpty": len([p for p in provider_logs if p.get("status") != "ok"]),
        }

    async def _run_ai_personality_analysis(
        self, query: str, github_res: Any, dorks_res: Any, corpus_text: str
    ) -> Dict[str, Any]:
        if self.ai_analyzer.is_configured():
            try:
                profile_data = {
                    "username": query,
                    "github": github_res,
                    "dorks": dorks_res,
                    "text": corpus_text,
                }
                res = await self.ai_analyzer.assess_risk(profile_data)
                if res.get("success"):
                    parsed = res.get("parsed") or {}
                    risk_level = parsed.get("risk_level", "LOW")
                    indicators = parsed.get("indicators") or []
                    recs = parsed.get("recommendations") or []
                    summary_text = (
                        f"Groq ({res.get('model_used', 'Llama-3.3-70B')}) Assessment: Risk Level {risk_level} (Score: {parsed.get('risk_score', 0)}/100). "
                        + (" ".join(recs[:1]) if recs else "")
                    )
                    return {
                        "primaryCategory": f"Evaluated Target ({res.get('model_used', 'Groq Llama-3.3-70B')})",
                        "confidence": 92,
                        "summary": summary_text,
                        "traits": indicators if indicators else ["public_profile_subject"],
                        "interests": ["osint_intelligence"],
                        "tone": risk_level.lower(),
                        "riskFlags": [{"label": ind, "severity": risk_level.lower()} for ind in indicators],
                        "model_used": res.get("model_used"),
                        "parsed": parsed,
                    }
            except Exception as exc:
                logger.warning("AIAnalyzer assess_risk error: %s", exc)

        categories = [
            ("Technology & Programming", ["code", "developer", "github", "tech", "python", "programming", "ai", "data", "software"]),
            ("Business & Entrepreneurship", ["business", "ceo", "founder", "startup", "company", "marketing", "sales", "executive"]),
            ("Arts & Creativity", ["art", "design", "music", "photo", "creative", "film", "artist", "writer"]),
            ("Sports & Fitness", ["sports", "fitness", "gym", "athlete", "cricket", "football", "workout"]),
        ]
        text_lower = corpus_text.lower()
        matched_cat = "General Public Profile"
        evidence = []
        max_hits = 0
        for cat_name, keywords in categories:
            hits = [kw for kw in keywords if kw in text_lower]
            if len(hits) > max_hits:
                max_hits = len(hits)
                matched_cat = cat_name
                evidence = hits

        confidence = min(95, 50 + max_hits * 15) if max_hits > 0 else 60

        return {
            "primaryCategory": matched_cat,
            "confidence": confidence,
            "summary": f"Profile indicators align with {matched_cat}.",
            "traits": evidence if evidence else ["active_online_presence"],
            "interests": evidence if evidence else ["general_osint_target"],
            "tone": "neutral",
            "riskFlags": [],
            "evidence": evidence,
        }
