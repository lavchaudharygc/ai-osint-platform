"""WhatsMyName (WMN) handle availability probing service across 700+ websites.
Ported from V1 wmn_service.py — local file first, remote URL fallback, cache.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Local bundled data file (same as V1)
DATA_FILE = Path(__file__).parent.parent / "data" / "wmn-data.json"
WMN_REMOTE_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"

_WMN_SITES: List[Dict[str, Any]] = []
_WMN_CACHE: Dict[str, Any] = {"data": None, "ts": 0}

BLOCK_PROTECTIONS = {"cloudflare", "captcha", "hcaptcha", "recaptcha"}


def _load_wmn_sites() -> List[Dict[str, Any]]:
    """Load WMN site definitions from local file first, then remote cache."""
    global _WMN_SITES
    if _WMN_SITES:
        return _WMN_SITES
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _WMN_SITES = data.get("sites", [])
                logger.info("Loaded %d WMN site templates from local file", len(_WMN_SITES))
        except Exception as exc:
            logger.error("Failed to load local WMN data: %s", exc)
    return _WMN_SITES


class WhatsMyNameService:
    """Probes username existence across 700+ websites concurrently.
    Uses local wmn-data.json (V1 approach) with optional remote fallback.
    """

    def __init__(self, concurrency: int = 40, timeout_seconds: float = 6.0):
        self.concurrency = concurrency
        self.timeout = timeout_seconds
        self.sites = _load_wmn_sites()

    async def _ensure_sites(self) -> List[Dict[str, Any]]:
        """Return loaded sites, fetching remote if local file had no data."""
        if self.sites:
            return self.sites
        # Try remote fallback
        now = time.time()
        if _WMN_CACHE["data"] and (now - _WMN_CACHE["ts"] < 3600):
            self.sites = _WMN_CACHE["data"]
            return self.sites
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(WMN_REMOTE_URL)
                if r.status_code == 200:
                    sites = r.json().get("sites", [])
                    if sites:
                        _WMN_CACHE["data"] = sites
                        _WMN_CACHE["ts"] = now
                        self.sites = sites
                        logger.info("Fetched %d WMN templates from remote", len(sites))
        except Exception as exc:
            logger.warning("WMN remote fallback failed: %s", exc)
        return self.sites

    async def _check_site(
        self, client: httpx.AsyncClient, site: Dict[str, Any], handle: str, sem: asyncio.Semaphore
    ) -> Dict[str, Any]:
        url = site.get("uri_check", "").replace("{account}", handle)
        name = site.get("name", "Unknown")
        cat = site.get("cat", "general")
        e_code = site.get("e_code", 200)
        m_code = site.get("m_code")
        e_string = site.get("e_string")
        m_string = site.get("m_string")
        protection = site.get("protection", [])
        is_protected = any(p.lower() in BLOCK_PROTECTIONS for p in protection)

        t0 = time.time()
        async with sem:
            try:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
                res = await client.get(url, headers=headers, follow_redirects=False, timeout=self.timeout)
                ms = int((time.time() - t0) * 1000)
                status_code = res.status_code

                if status_code in (403, 429, 503):
                    return {"site": name, "category": cat, "url": url, "status": "blocked", "ms": ms, "handle": handle}

                if status_code == e_code:
                    if e_string:
                        text = res.text
                        if e_string in text:
                            return {"site": name, "category": cat, "url": url, "status": "found", "ms": ms, "handle": handle}
                        if m_string and m_string in text:
                            return {"site": name, "category": cat, "url": url, "status": "not_found", "ms": ms, "handle": handle}
                        return {"site": name, "category": cat, "url": url, "status": "unknown", "ms": ms, "handle": handle}
                    return {"site": name, "category": cat, "url": url, "status": "found", "ms": ms, "handle": handle}

                if m_code and status_code == m_code:
                    return {"site": name, "category": cat, "url": url, "status": "not_found", "ms": ms, "handle": handle}

                return {"site": name, "category": cat, "url": url, "status": "blocked" if is_protected else "not_found", "ms": ms, "handle": handle}

            except (httpx.TimeoutException, httpx.NetworkError):
                ms = int((time.time() - t0) * 1000)
                return {"site": name, "category": cat, "url": url, "status": "blocked" if is_protected else "unknown", "ms": ms, "handle": handle}
            except Exception:
                ms = int((time.time() - t0) * 1000)
                return {"site": name, "category": cat, "url": url, "status": "unknown", "ms": ms, "handle": handle}

    async def probe_username(self, username: str, site_cap: Optional[int] = None) -> Dict[str, Any]:
        """Run full WMN probe, same interface as scan_handle in V1."""
        clean_handle = username.strip().lstrip("@")
        if not clean_handle:
            return {"status": "error", "scanned": 0, "hits_count": 0, "hits": []}

        target_sites = await self._ensure_sites()
        if not target_sites:
            return {"status": "error", "message": "No WMN templates available", "scanned": 0, "hits_count": 0, "hits": []}

        if site_cap and site_cap > 0:
            target_sites = target_sites[:site_cap]

        sem = asyncio.Semaphore(self.concurrency)
        t_start = time.time()

        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        async with httpx.AsyncClient(limits=limits, verify=False) as client:
            tasks = [self._check_site(client, site, clean_handle, sem) for site in target_sites]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        duration_ms = int((time.time() - t_start) * 1000)
        valid_results = [r for r in results if isinstance(r, dict)]
        found_hits = [r for r in valid_results if r.get("status") == "found"]

        return {
            "status": "success",
            "handle": clean_handle,
            "scanned": len(target_sites),
            "hits_count": len(found_hits),
            "found_count": len(found_hits),  # compat alias
            "hits": found_hits,
            "duration_ms": duration_ms,
        }

    # Alias for backward compat with any caller using scan_handle
    async def scan_handle(self, handle: str, site_cap: Optional[int] = None) -> Dict[str, Any]:
        return await self.probe_username(handle, site_cap)
