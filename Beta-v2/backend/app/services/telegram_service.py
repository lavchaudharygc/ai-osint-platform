"""Telegram service for Beta-v2: MTProto preview & CTI breach lookups.
Integrates with leakosintapi.com API with Depth-2 recursive enrichment.
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List
from app.config import settings

from app.services.telegram_cti_service import fetch_cti, fetchCTI

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self):
        self.cti_key = settings.telegram_cti_api_key

    async def search_cti_breaches(self, queries: List[str]) -> Dict[str, Any]:
        """Query CTI under the server-owned privacy and quota ceilings."""

        return await fetch_cti(
            queries,
            limit=settings.telegram_cti_default_limit,
            max_depth=settings.telegram_cti_max_depth,
            max_total_searches=settings.telegram_cti_max_logical_searches,
            max_http_attempts=settings.telegram_cti_max_http_attempts,
            max_retries_per_query=settings.telegram_cti_max_retries_per_query,
        )
