"""
Telegram CTI (Cyber Threat Intelligence) Service
Integrates with @Mr_EverythingPDX_bot API (https://leakosintapi.com/) for breach data lookups
"""

import asyncio
import logging
import time
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

from backend.core.config import settings

logger = logging.getLogger(__name__)

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

# ============================================================
# SERVICE CLASS
# ============================================================

class TelegramCTIService:
    """
    Service for interacting with @Mr_EverythingPDX_bot API
    Provides breach intelligence from multiple leak databases.
    search() is async-safe: blocking I/O runs in a thread pool via asyncio.to_thread().
    Includes exponential-backoff retry on HTTP 429 (max 3 attempts).
    """

    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 1.0  # seconds; doubles each attempt

    def __init__(self):
        self.api_url = "https://leakosintapi.com/"
        self.token = settings.telegram_cti_api_key
        self.default_limit = getattr(settings, "telegram_cti_default_limit", 100)
        self.default_lang = "en"
        self.timeout = 30

        if not self.token:
            logger.warning("TELEGRAM_CTI_API_KEY not set in .env")

    def is_configured(self) -> bool:
        return bool(self.token)

    async def search(self, query: str, limit: int = 100, lang: str = "en") -> CTIResponse:
        """Async-safe search: runs blocking HTTP call in a thread-pool worker."""
        if not self.token:
            return CTIResponse(
                status="error",
                error="TELEGRAM_CTI_API_KEY not configured",
                query=query
            )
        return await asyncio.to_thread(self._search_sync, query, limit, lang)

    def _search_sync(self, query: str, limit: int, lang: str) -> CTIResponse:
        """Blocking HTTP search with exponential-backoff retry on 429."""
        payload = {
            "token": self.token,
            "request": query,
            "limit": limit,
            "lang": lang
        }
        logger.info(f"CTI Search: {query[:50]}... (limit: {limit})")

        last_error: Optional[str] = None
        for attempt in range(self._MAX_RETRIES):
            try:
                response = requests.post(
                    self.api_url,
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    raw_data = response.json()
                    return self._parse_response(raw_data, query)

                if response.status_code == 429:
                    delay = self._RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"CTI API rate-limited (429) for query '{query[:30]}', "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{self._MAX_RETRIES})"
                    )
                    time.sleep(delay)
                    last_error = f"Rate limited (429) after {self._MAX_RETRIES} retries"
                    continue

                logger.error(f"CTI API error: {response.status_code} - {response.text[:200]}")
                return CTIResponse(
                    status="error",
                    error=f"API returned {response.status_code}",
                    query=query,
                    raw_response={"status_code": response.status_code}
                )

            except requests.exceptions.Timeout:
                logger.error("CTI API timeout")
                return CTIResponse(status="error", error="Request timeout", query=query)
            except requests.exceptions.RequestException as e:
                logger.error(f"CTI API request error: {e}")
                return CTIResponse(status="error", error=str(e), query=query)
            except Exception as e:
                logger.error(f"CTI service error: {e}")
                return CTIResponse(
                    status="error",
                    error=f"Service error: {str(e)}",
                    query=query
                )

        # All retries exhausted (only reached via 429 loop)
        return CTIResponse(status="error", error=last_error or "Max retries exceeded", query=query)

    def _parse_response(self, raw_data: Dict, query: str) -> CTIResponse:
        """Parse raw API response into structured CTI results"""
        if "Error code" in raw_data:
            return CTIResponse(
                status="error",
                error=f"API Error: {raw_data['Error code']}",
                query=query,
                raw_response=raw_data
            )

        results = []
        list_data = raw_data.get("List", {})

        if isinstance(list_data, dict):
            for database_name, db_data in list_data.items():
                if database_name == "No results found":
                    continue

                if isinstance(db_data, dict):
                    data_entries = db_data.get("Data", [])
                    if data_entries:
                        results.append(CTIResult(
                            database=database_name,
                            data=data_entries if isinstance(data_entries, list) else [data_entries],
                            info_leak=db_data.get("InfoLeak")
                        ))

        return CTIResponse(
            status="success" if results else "no_results",
            results=results,
            query=query,
            raw_response=raw_data
        )

# Singleton helper
_cti_service: Optional[TelegramCTIService] = None

def get_cti_service() -> TelegramCTIService:
    global _cti_service
    if _cti_service is None:
        _cti_service = TelegramCTIService()
    return _cti_service
