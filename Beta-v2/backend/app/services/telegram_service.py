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
        """Query leakosintapi.com for breach databases matching target identifiers with depth-2 search."""
        return await fetch_cti(queries)
