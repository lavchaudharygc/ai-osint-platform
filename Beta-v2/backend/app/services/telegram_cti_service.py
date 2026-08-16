"""
Telegram CTI (Cyber Threat Intelligence) Service
Integrates with @Mr_EverythingPDX_bot API (https://leakosintapi.com/) for breach data lookups
Includes depth-2 recursive enrichment loop and TELEGRAM_CTI_ENABLED checks.
"""

import asyncio
import logging
import os
import re
import time
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
import httpx
from pydantic import BaseModel, Field

from app.config import settings

logger = logging.getLogger(__name__)
_LEGACY_FALLBACK_TOKEN = "8978542043:3e22t6sI"


# ============================================================
# PYDANTIC MODELS
# ============================================================

class CTISearchRequest(BaseModel):
    """Request model for CTI search"""
    query: str = Field(..., description="Search query (email, username, phone, name, etc.)")
    limit: int = Field(default=100, ge=10, le=10000, description="Search limit")
    lang: str = Field(default="en", description="Response language")


class CTIResult(BaseModel):
    """Single CTI result from a database"""
    database: str
    data: List[Dict[str, Any]]
    info_leak: Optional[str] = None


class CTIResponse(BaseModel):
    """Complete CTI API response"""
    status: str = "success"
    results: List[CTIResult] = []
    error: Optional[str] = None
    raw_response: Optional[Dict] = None
    query: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


def _resolve_cti_token() -> str | None:
    token = settings.telegram_cti_api_key or os.getenv("TELEGRAM_CTI_API_KEY")
    cleaned = str(token or "").strip()
    return cleaned if cleaned else None


def _extract_api_error(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("Error code", "error", "message", "detail", "Status"):
            value = payload.get(key)
            if value and str(value).strip().casefold() != "error":
                return str(value).strip()
        if payload.get("Status") == "Error":
            return "LeakOSINT API returned an error."
    if isinstance(payload, str):
        cleaned = payload.strip()
        if cleaned:
            return cleaned
    return None


def extract_identifiers_from_rows(rows: List[Dict[str, Any]]) -> Set[str]:
    """Extract emails, phones, and usernames from breach data rows for depth-2 search."""
    discovered: Set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for k, v in row.items():
            if not v or not isinstance(v, (str, int)):
                continue
            val_str = str(v).strip()
            if len(val_str) < 3:
                continue
            k_lower = str(k).lower()

            # Email match
            if "@" in val_str and "." in val_str and " " not in val_str:
                discovered.add(val_str)
            # Phone match
            elif "phone" in k_lower or "mobile" in k_lower or "tel" in k_lower:
                digits = re.sub(r"\D", "", val_str)
                if len(digits) >= 10:
                    discovered.add(val_str)
            # Username match
            elif "username" in k_lower or "login" in k_lower or "handle" in k_lower:
                if len(val_str) >= 3 and " " not in val_str and "@" not in val_str:
                    discovered.add(val_str)
    return discovered


async def fetch_cti(
    query: str | List[str],
    limit: int = 100,
    max_depth: int = 2,
    max_total_searches: int = 15,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Dict[str, Any]:
    """Standalone Telegram CTI fetch with Depth-2 enrichment loop."""
    enabled_val = os.getenv("TELEGRAM_CTI_ENABLED")
    if enabled_val is not None and enabled_val.lower().strip() != "true":
        return {"skipped": True, "status": "skipped", "total_records": 0, "results": []}

    token = _resolve_cti_token()
    if not token:
        return {
            "query": query[0] if isinstance(query, list) and query else (query if isinstance(query, str) else ""),
            "searches_performed": 0,
            "total_records": 0,
            "totalRecords": 0,
            "databases": [],
            "results": [],
            "status": "not_configured",
            "error": "TELEGRAM_CTI_API_KEY not configured",
        }

    initial_queries = [query] if isinstance(query, str) else list(query)
    clean_initial = list(
        dict.fromkeys(q.strip() for q in initial_queries if q and len(q.strip()) >= 3)
    )
    if not clean_initial:
        raise ValueError("Query too short")

    searched: Set[str] = set()
    queued: Set[str] = set(clean_initial)
    results: List[Dict[str, Any]] = []
    databases_found: Set[str] = set()
    total_records = 0
    last_error: Optional[str] = None

    url = "https://leakosintapi.com/"
    semaphore = asyncio.Semaphore(3)
    effective_limit = max(1, min(int(limit), 10000))

    async def _query_api(q: str, client: httpx.AsyncClient) -> tuple[str, Dict[str, Any] | None, str | None]:
        async with semaphore:
            payload = {"token": token, "request": q, "limit": effective_limit, "lang": "en"}
            for attempt in range(3):
                try:
                    resp = await client.post(url, json=payload)
                    raw_data: Any = None
                    parsed_error: str | None = None
                    try:
                        raw_data = resp.json()
                        parsed_error = _extract_api_error(raw_data)
                    except ValueError:
                        parsed_error = _extract_api_error(resp.text)

                    is_transient_error = (
                        resp.status_code in (429, 502, 503, 504)
                        or (parsed_error and any(
                            err_pattern in parsed_error.lower()
                            for err_pattern in ("make requests again", "too many requests", "502", "503", "bad gateway", "service unavailable")
                        ))
                    )
                    if is_transient_error and attempt < 2:
                        await asyncio.sleep(2.0 * (attempt + 1))
                        continue

                    if resp.status_code == 200:
                        if parsed_error:
                            return q, None, parsed_error
                        return q, raw_data if isinstance(raw_data, dict) else {}, None

                    message = parsed_error or f"HTTP {resp.status_code}"
                    return q, None, message
                except Exception as exc:
                    if attempt < 2:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    return q, None, str(exc)
            return q, None, "Rate limit exceeded"

    current_queue = list(clean_initial)
    current_depth = 1

    async with httpx.AsyncClient(timeout=25.0, transport=transport) as client:
        while current_queue and current_depth <= max_depth and len(searched) < max_total_searches:
            batch = current_queue[: (max_total_searches - len(searched))]
            current_queue = []
            searched.update(batch)

            tasks = [_query_api(q, client) for q in batch]
            responses = await asyncio.gather(*tasks)

            next_depth_candidates: Set[str] = set()

            for q, raw_data, err in responses:
                if err:
                    last_error = err
                    continue
                if not raw_data:
                    continue

                list_data = raw_data.get("List", {})
                if not isinstance(list_data, dict):
                    continue

                for db_name, db_val in list_data.items():
                    if db_name in {"No results found", "No money", "No money left", "Invalid token"}:
                        continue
                    if isinstance(db_val, dict):
                        entries = db_val.get("Data", [])
                        rows = entries if isinstance(entries, list) else ([entries] if entries else [])
                        if rows:
                            databases_found.add(db_name)
                            total_records += len(rows)
                            results.append({
                                "query": q,
                                "database": db_name,
                                "info_leak": db_val.get("InfoLeak"),
                                "rows": rows,
                                "data": rows,
                            })
                            if current_depth < max_depth:
                                extracted = extract_identifiers_from_rows(rows)
                                next_depth_candidates.update(extracted)

            new_queries = [
                cand for cand in next_depth_candidates
                if cand not in searched and cand not in queued
            ]
            queued.update(new_queries)
            current_queue = new_queries
            current_depth += 1

    primary_q = clean_initial[0] if clean_initial else ""
    return {
        "query": primary_q,
        "searches_performed": len(searched),
        "total_records": total_records,
        "totalRecords": total_records,
        "databases": list(databases_found),
        "results": results,
        "status": "error" if (not results and last_error) else ("success" if results else "no_results"),
        "error": last_error if (not results and last_error) else None,
    }


fetchCTI = fetch_cti


# ============================================================
# SERVICE CLASS
# ============================================================

class TelegramCTIService:
    """Service for interacting with @Mr_EverythingPDX_bot API (LeakOSINT API)."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        self.api_url = "https://leakosintapi.com/"
        self.token = _resolve_cti_token()
        self.default_limit = getattr(settings, "telegram_cti_default_limit", 100)
        self.default_lang = "en"
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self.token)

    async def search(self, query: str, limit: int = 100, lang: str = "en") -> CTIResponse:
        """Execute CTI search with depth-2 enrichment."""
        res = await fetch_cti(query, limit=limit, transport=self._transport)
        results = [
            CTIResult(
                database=r.get("database", ""),
                data=r.get("rows", []),
                info_leak=r.get("info_leak"),
            )
            for r in res.get("results", [])
        ]
        return CTIResponse(
            status=res.get("status", "success"),
            results=results,
            error=res.get("error"),
            query=res.get("query", query),
        )

    async def health_check(self) -> dict[str, Any]:
        """Run a safe live provider probe without querying a real target."""
        checked_at = datetime.now().isoformat()
        probe_limit = 100
        if not getattr(settings, "telegram_cti_enabled", True):
            return {
                "provider": "leakosintapi",
                "configured": False,
                "enabled": False,
                "status": "disabled",
                "outcome": "disabled",
                "checked_at": checked_at,
                "provider_message": "TELEGRAM_CTI_ENABLED is false",
                "raw_provider_response": None,
            }
        if not self.token:
            return {
                "provider": "leakosintapi",
                "configured": False,
                "enabled": True,
                "status": "not_configured",
                "outcome": "not_configured",
                "checked_at": checked_at,
                "provider_message": "TELEGRAM_CTI_API_KEY not configured",
                "raw_provider_response": None,
            }

        payload = {
            "token": self.token,
            "request": "telegram_cti_healthcheck",
            "limit": probe_limit,
            "lang": self.default_lang,
        }
        try:
            async with httpx.AsyncClient(timeout=25.0, transport=self._transport) as client:
                response = await client.post(self.api_url, json=payload)
        except Exception as exc:
            return {
                "provider": "leakosintapi",
                "configured": True,
                "enabled": True,
                "status": "error",
                "outcome": "network_error",
                "checked_at": checked_at,
                "provider_message": str(exc),
                "raw_provider_response": None,
            }

        raw_text = response.text
        raw_json: Any = None
        provider_message: str | None = None
        try:
            raw_json = response.json()
            provider_message = _extract_api_error(raw_json)
        except ValueError:
            provider_message = _extract_api_error(raw_text)

        outcome = "ok"
        status = "healthy"
        lower_message = str(provider_message or "").casefold()
        if response.status_code >= 400:
            outcome = "provider_error"
            status = "error"
            if "invalid data" in lower_message or "able to make requests again" in lower_message:
                outcome = "rate_limited"
                status = "degraded"
        elif provider_message:
            outcome = "provider_error"
            status = "error"
            if "don't have a premium" in lower_message or "subscription" in lower_message or "shop page" in lower_message:
                outcome = "premium_required"
                status = "degraded"

        return {
            "provider": "leakosintapi",
            "configured": True,
            "enabled": True,
            "status": status,
            "outcome": outcome,
            "checked_at": checked_at,
            "http_status_code": response.status_code,
            "provider_message": provider_message,
            "raw_provider_response": raw_json if raw_json is not None else raw_text[:2000],
            "probe_request": {
                "request": "telegram_cti_healthcheck",
                "limit": probe_limit,
                "lang": self.default_lang,
            },
        }


_cti_service: Optional[TelegramCTIService] = None

def get_cti_service() -> TelegramCTIService:
    global _cti_service
    if _cti_service is None:
        _cti_service = TelegramCTIService()
    return _cti_service
