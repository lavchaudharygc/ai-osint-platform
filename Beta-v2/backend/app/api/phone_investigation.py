"""Authenticated, audited, single-target phone-investigation endpoint."""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.schemas.phone_investigation import (
    PhoneInvestigationRequest,
    PhoneInvestigationResponse,
)
from app.security.audit import AuditEvent, AuditReceipt, AuditUnavailable, get_audit_logger
from app.security.auth import AuthenticatedUser, require_csrf, require_roles
from app.services.phone_investigation_service import PhoneInvestigationService

router = APIRouter(prefix="/api/v1/phone-investigation", tags=["phone-investigation"])
require_phone_investigator = require_roles("investigator")
logger = logging.getLogger(__name__)


def get_phone_investigation_service() -> PhoneInvestigationService:
    """Construct a request-scoped service without exposing provider settings."""
    return PhoneInvestigationService()


@router.post("", response_model=PhoneInvestigationResponse)
async def run_phone_investigation(
    request: PhoneInvestigationRequest,
    response: Response,
    user: AuthenticatedUser = Depends(require_phone_investigator),
    csrf: None = Depends(require_csrf),
    service: PhoneInvestigationService = Depends(get_phone_investigation_service),
) -> PhoneInvestigationResponse:
    """Execute a bounded phone number investigation."""

    started = time.monotonic()
    logger.info(
        "event=phone_investigation_started breach_requested=%s "
        "web_discovery_requested=%s social_requested=%s",
        request.include_breaches,
        request.include_web_dorks,
        request.include_social,
    )
    response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
    result = await service.investigate(request)
    result.authorization.authenticated_user = user.username
    result.authorization.roles = list(user.roles)
    logger.info(
        "event=phone_investigation_completed investigation_id=%s result_status=%s "
        "breach_status=%s web_status=%s social_status=%s elapsed_ms=%d",
        result.investigation_id,
        result.status,
        result.breach_discovery.status,
        result.web_discovery.status,
        result.social_discovery.status,
        round((time.monotonic() - started) * 1000),
    )
    return result
