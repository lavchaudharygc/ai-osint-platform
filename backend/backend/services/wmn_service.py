"""WhatsMyName (WMN) handle availability probing service across 700+ websites."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent / "data" / "wmn-data.json"

_WMN_SITES: List[Dict[str, Any]] = []


def _load_wmn_sites() -> List[Dict[str, Any]]:
    global _WMN_SITES
    if _WMN_SITES:
        return _WMN_SITES
    if not DATA_FILE.exists():
        logger.warning("wmn-data.json file missing at %s", DATA_FILE)
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            _WMN_SITES = data.get("sites", [])
            logger.info("Loaded %d WhatsMyName site probe definitions", len(_WMN_SITES))
    except Exception as exc:
        logger.error("Failed to load WhatsMyName sites: %s", exc)
        _WMN_SITES = []
    return _WMN_SITES


BLOCK_PROTECTIONS = {"cloudflare", "captcha", "hcaptcha", "recaptcha"}


class WhatsMyNameService:
    """Probes username existence across 700+ websites concurrently."""

    def __init__(self, concurrency: int = 40, timeout_seconds: float = 6.0):
        self.concurrency = concurrency
        self.timeout = timeout_seconds
        self.sites = _load_wmn_sites()

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

    async def scan_handle(
        self, handle: str, site_cap: Optional[int] = None
    ) -> Dict[str, Any]:
        clean_handle = handle.strip().lstrip("@")
        if not clean_handle:
            return {"scanned": 0, "found_count": 0, "hits": [], "duration_ms": 0}

        target_sites = self.sites[:site_cap] if site_cap and site_cap > 0 else self.sites
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
            "handle": clean_handle,
            "scanned": len(valid_results),
            "found_count": len(found_hits),
            "hits": found_hits,
            "duration_ms": duration_ms,
        }
