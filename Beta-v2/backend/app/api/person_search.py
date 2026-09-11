"""Authenticated, audited, full-name public-profile search endpoints."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.schemas.person_search import (
    PersonSearchRequest,
    PersonSearchResponse,
    PersonSearchStatusResponse,
)
from app.security.audit import AuditEvent, AuditReceipt, AuditUnavailable, get_audit_logger
from app.security.auth import AuthenticatedUser, require_csrf, require_roles
from app.services.person_search.service import PersonSearchService


logger = logging.getLogger(__name__)


class _NoStoreValidationRoute(APIRoute):
    """Suppress rejected request values and prohibit caching route-level 422s."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_handler = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                safe_errors = []
                for _error in exc.errors():
                    safe_errors.append(
                        {
                            "type": "validation_error",
                            # Do not echo rejected field names: extra JSON keys
                            # can themselves contain sensitive target material.
                            "loc": ["body"],
                            "msg": "Invalid person-search request value",
                        }
                    )
                logger.warning(
                    "event=person_search_validation_rejected error_count=%d",
                    max(1, len(safe_errors)),
                )
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": safe_errors or [{
                        "type": "validation_error",
                        "loc": ["body"],
                        "msg": "Invalid person-search request",
                    }]},
                    headers={
                        "Cache-Control": "no-store, private",
                        "Pragma": "no-cache",
                    },
                )

        return safe_handler


router = APIRouter(
    prefix="/api/v1/person-search",
    tags=["person-search"],
    route_class=_NoStoreValidationRoute,
)
require_person_search_investigator = require_roles("investigator")


def get_person_search_service() -> PersonSearchService:
    """Construct a request-scoped service without exposing provider settings."""

    return PersonSearchService()


async def _record_person_search_access(
    *,
    user: AuthenticatedUser,
    request: PersonSearchRequest,
    case_id: str,
    outcome: str,
    field_labels: tuple[str, ...] = (),
) -> AuditReceipt:
    """Write a target-HMACed audit event or fail without disclosing results."""

    try:
        event = AuditEvent(
            analyst=user.username,
            action="person_search.public_profiles",
            outcome=outcome,
            case_id=case_id,
            reason_code=request.reason_code,
            target=request.full_name,
            field_labels=field_labels,
        )
        return await asyncio.to_thread(get_audit_logger().record, event)
    except AuditUnavailable as exc:
        logger.error(
            "event=person_search_audit_unavailable outcome=%s error_type=%s",
            outcome,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Person-search audit is unavailable",
            headers={"Cache-Control": "no-store"},
        ) from exc


def _result_field_labels(result: PersonSearchResponse) -> tuple[str, ...]:
    labels: set[str] = set()
    if result.profiles:
        labels.update(("profile_url", "username"))
    if any(profile.full_name for profile in result.profiles):
        labels.add("full_name")
    if result.photos:
        labels.add("photo_url")
    return tuple(sorted(labels))


@router.get("/status", response_model=PersonSearchStatusResponse)
async def person_search_status(
    response: Response,
    _user: AuthenticatedUser = Depends(require_person_search_investigator),
    service: PersonSearchService = Depends(get_person_search_service),
) -> PersonSearchStatusResponse:
    """Return non-secret readiness and hard server ceilings."""

    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return service.status()


@router.post("", response_model=PersonSearchResponse)
async def person_search(
    request: PersonSearchRequest,
    response: Response,
    user: AuthenticatedUser = Depends(require_person_search_investigator),
    _csrf_user: AuthenticatedUser = Depends(require_csrf),
    service: PersonSearchService = Depends(get_person_search_service),
) -> PersonSearchResponse:
    """Find bounded public profile candidates for one full name."""

    investigation_id = f"UPP-{uuid4().hex[:8].upper()}"
    case_id = request.case_id or investigation_id
    started = time.monotonic()
    requested_receipt = await _record_person_search_access(
        user=user,
        request=request,
        case_id=case_id,
        outcome="requested",
    )
    logger.info(
        "event=person_search_started investigation_id=%s platform_count=%d "
        "query_limit=%d profile_limit=%d audit_event_id=%s",
        investigation_id,
        len(request.platforms),
        request.query_limit,
        request.max_profiles,
        requested_receipt.event_id,
    )
    try:
        result = await service.search(
            request,
            investigation_id=investigation_id,
            case_id=case_id,
        )
    except Exception as exc:
        logger.error(
            "event=person_search_failed investigation_id=%s elapsed_ms=%d error_type=%s",
            investigation_id,
            round((time.monotonic() - started) * 1000),
            type(exc).__name__,
        )
        await _record_person_search_access(
            user=user,
            request=request,
            case_id=case_id,
            outcome="failed",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Person search could not be completed",
            headers={"Cache-Control": "no-store"},
        ) from exc

    audit_outcome = {
        "completed": "success",
        "partial": "partial",
        "no_results": "no_results",
    }.get(result.status, result.status)
    receipt = await _record_person_search_access(
        user=user,
        request=request,
        case_id=case_id,
        outcome=audit_outcome,
        field_labels=_result_field_labels(result),
    )
    result.audit_event_id = receipt.event_id
    provider_error = result.errors[0].code if result.errors else "none"
    logger.info(
        "event=person_search_completed investigation_id=%s result_status=%s "
        "provider_error=%s profiles=%d queries_attempted=%d queries_completed=%d "
        "elapsed_ms=%d audit_event_id=%s",
        investigation_id,
        result.status,
        provider_error,
        result.counts.profiles,
        result.counts.queries_attempted,
        result.counts.queries_completed,
        round((time.monotonic() - started) * 1000),
        receipt.event_id,
    )
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return result


__all__ = [
    "get_person_search_service",
    "require_person_search_investigator",
    "router",
]
