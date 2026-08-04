"""WhatsMyName 700+ site probe service for Beta-v2."""

import asyncio
import time
import httpx
from typing import Any, Dict, List

WMN_RESOURCES_URL = "https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json"
_WMN_CACHE: Dict[str, Any] = {"data": None, "ts": 0}


class WhatsMyNameService:
    def __init__(self, timeout_seconds: float = 8.0, max_concurrent: int = 40):
        self.timeout = timeout_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_sites(self) -> List[Dict[str, Any]]:
        now = time.time()
        if _WMN_CACHE["data"] and (now - _WMN_CACHE["ts"] < 3600):
            return _WMN_CACHE["data"]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(WMN_RESOURCES_URL)
                if r.status_code == 200:
                    sites = r.json().get("sites", [])
                    _WMN_CACHE["data"] = sites
                    _WMN_CACHE["ts"] = now
                    return sites
        except Exception:
            pass
        return _WMN_CACHE.get("data") or []

    async def _check_site(self, client: httpx.AsyncClient, site: Dict[str, Any], username: str) -> Dict[str, Any] | None:
        uri_check = site.get("uri_check", "").replace("{account}", username)
        if not uri_check:
            return None

        e_code = site.get("e_code")
        e_string = site.get("e_string")
        m_code = site.get("m_code")
        m_string = site.get("m_string")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        t0 = time.time()
        async with self.semaphore:
            try:
                r = await client.get(uri_check, headers=headers, follow_redirects=True, timeout=self.timeout)
                ms = int((time.time() - t0) * 1000)

                body = r.text
                found = False

                if e_code and r.status_code == e_code:
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
                        "site": site.get("name"),
                        "category": site.get("cat", "general"),
                        "url": uri_check,
                        "ms": ms,
                        "handle": username,
                    }
            except Exception:
                return None
        return None

    async def probe_username(self, username: str, limit: int = 150) -> Dict[str, Any]:
        sites = await self.fetch_sites()
        if not sites:
            return {"status": "error", "message": "Failed to fetch WMN templates", "hits": [], "scanned": 0}

        target_sites = sites[:limit]
        async with httpx.AsyncClient(verify=False) as client:
            tasks = [self._check_site(client, s, username) for s in target_sites]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        hits = [r for r in results if isinstance(r, dict) and r is not None]
        return {
            "status": "success",
            "scanned": len(target_sites),
            "total_templates": len(sites),
            "hits_count": len(hits),
            "hits": hits,
        }
