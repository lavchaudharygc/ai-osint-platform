"""WhatsMyName (WMN) handle availability probing service across 700+ websites for Beta-v2."""

import asyncio
import time
import logging
from typing import Any, Dict, List
import httpx

logger = logging.getLogger(__name__)

WMN_RESOURCES_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
_WMN_CACHE: Dict[str, Any] = {"data": None, "ts": 0}


class WhatsMyNameService:
    def __init__(self, concurrency: int = 50, timeout_seconds: float = 6.0):
        self.concurrency = concurrency
        self.timeout = timeout_seconds

    async def fetch_sites(self) -> List[Dict[str, Any]]:
        now = time.time()
        if _WMN_CACHE["data"] and (now - _WMN_CACHE["ts"] < 3600):
            return _WMN_CACHE["data"]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(WMN_RESOURCES_URL)
                if r.status_code == 200:
                    sites = r.json().get("sites", [])
                    if sites:
                        _WMN_CACHE["data"] = sites
                        _WMN_CACHE["ts"] = now
                        return sites
        except Exception as exc:
            logger.warning("Failed to fetch WMN remote sites: %s", exc)

        return _WMN_CACHE.get("data") or []

    async def _check_site(
        self, client: httpx.AsyncClient, site: Dict[str, Any], handle: str, sem: asyncio.Semaphore
    ) -> Dict[str, Any] | None:
        url = site.get("uri_check", "").replace("{account}", handle)
        if not url:
            return None

        name = site.get("name", "Unknown")
        cat = site.get("cat", "general")
        e_code = site.get("e_code", 200)
        e_string = site.get("e_string")
        m_code = site.get("m_code")
        m_string = site.get("m_string")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        t0 = time.time()
        async with sem:
            try:
                r = await client.get(url, headers=headers, follow_redirects=True, timeout=self.timeout)
                ms = int((time.time() - t0) * 1000)

                body = r.text
                found = False

                if r.status_code == e_code:
                    if e_string:
                        if e_string in body:
                            found = True
                    else:
                        found = True

                if not found and e_string and e_string in body:
                    found = True

                if found and m_string and m_string in body:
                    found = False
                if found and m_code and r.status_code == m_code:
                    found = False

                if found:
                    return {
                        "site": name,
                        "category": cat,
                        "url": url,
                        "status": "found",
                        "ms": ms,
                        "handle": handle,
                    }
            except Exception:
                return None
        return None

    async def probe_username(self, username: str) -> Dict[str, Any]:
        clean_handle = username.strip().lstrip("@")
        if not clean_handle:
            return {"status": "error", "scanned": 0, "hits_count": 0, "hits": []}

        sites = await self.fetch_sites()
        if not sites:
            return {"status": "error", "message": "No WMN templates available", "scanned": 0, "hits_count": 0, "hits": []}

        sem = asyncio.Semaphore(self.concurrency)
        t0 = time.time()

        limits = httpx.Limits(max_keepalive_connections=30, max_connections=100)
        async with httpx.AsyncClient(limits=limits, verify=False) as client:
            tasks = [self._check_site(client, s, clean_handle, sem) for s in sites]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        duration_ms = int((time.time() - t0) * 1000)
        hits = [r for r in results if isinstance(r, dict) and r is not None]

        return {
            "status": "success",
            "handle": clean_handle,
            "scanned": len(sites),
            "hits_count": len(hits),
            "hits": hits,
            "duration_ms": duration_ms,
        }
